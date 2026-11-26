"""按审查阶段约束输出，保留未完成回查的初审意见。"""
import json,re
from urllib.parse import urlsplit


def object_schema(**fields):
    return {"type": "object", "properties": fields, "required": list(fields),
            "additionalProperties": False}


def array_schema(item, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum}


def enum_schema(*values):
    return {"type": "string", "enum": list(values)}


def stage_schemas(categories, priorities):
    text = {"type": "string", "minLength": 1}
    quote = object_schema(source=text, paragraph={"type": "integer", "minimum": 1}, quote=text)
    citations = array_schema(quote, 1)
    issue = object_schema(category=enum_schema(*categories), priority=enum_schema(*priorities),
                          priorityReason=text, title=text, description=text, suggestion=text, citations=citations,basis=array_schema(object_schema(ref=text,clause_quote=text,relation=enum_schema("违反","未落实","参照"),reason=text)))
    parameter = object_schema(name=text, value=text, scope=text, citations=citations)
    focus_result = object_schema(focus=text, status=enum_schema("发现问题", "已检视未发现", "需补充资料"), summary=text)
    fields = {"issues": array_schema(issue), "parameters": array_schema(parameter),
              "focusResults": array_schema(focus_result)}
    review_fields = {"candidateIds": array_schema(text, 1), "reason": text, "evidence": citations}
    review = {"anyOf": [
        object_schema(**review_fields, decision=enum_schema("保留", "待核"), issue=issue),
        object_schema(**review_fields, decision=enum_schema("排除"), issue={"type": "null"}),
    ]}
    merge = object_schema(issueIds=array_schema(text, 2), issue=issue)
    return {
        "初审": ("review_initial", object_schema(**fields)),
        "设计提取": ("review_design", object_schema(**fields)),
        "全篇回查": ("review_verify", object_schema(reviews=array_schema(review))),
        "最终汇总": ("review_finish", object_schema(mergeGroups=array_schema(merge), **fields)),
    }


def configure_qwen_request(cfg, body, phase, schemas):
    host = urlsplit(cfg["base"]).hostname
    if host != "maas.qianwenaiapi.com" or body["model"] != "qwen4-max" or phase not in schemas:
        return
    body["enable_thinking"] = bool(cfg.get("thinking", True))
    if "response_format" in body:
        name, schema = schemas[phase]
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": name, "strict": True, "schema": schema}}


ISSUE_FIELDS = {"title": "问题标题", "description": "问题描述", "suggestion": "修改建议",
                "priorityReason": "优先级理由"}
TRAILING_CLAUSE = re.compile(r"(?:[，：、,:；;]|但|但是|因为|例如|包括|仅列|只列|如下)$")


def check_citations(engine, values, refs, allowed):
    if isinstance(values, list) and any(isinstance(cite, dict) and not isinstance(cite.get("source"), str)
                                        for cite in values):
        raise ValueError("引用来源格式错误。")
    return engine["checked_citations"](values, refs, allowed)


def review_errors(entry, refs, allowed, engine):
    """列出具体缺失的字段或无法核验的引文。"""
    errors = []
    if entry.get("decision") not in ("保留", "待核", "排除"):
        errors.append("处理结论不正确")
    if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
        errors.append("缺少复核理由（reason）")

    try:
        check_citations(engine, entry.get("evidence"), refs, allowed)
    except ValueError as exc:
        errors.append(f"复核依据（evidence）：{exc}")

    if entry.get("decision") == "排除":
        return errors
    issue = entry.get("issue")
    if not isinstance(issue, dict):
        return errors + ["缺少回查问题（issue）"]
    for key, label in ISSUE_FIELDS.items():
        value = issue.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"缺少{label}（issue.{key}）")
        elif key in ("description", "suggestion") and TRAILING_CLAUSE.search(value.strip()):
            errors.append(f"{label}未写完整（issue.{key}）")
    if issue.get("category") not in engine["CATEGORIES"]:
        errors.append("问题类别不正确（issue.category）")
    if not isinstance(issue.get("priority"), str) or issue["priority"] not in engine["PRIORITIES"]:
        errors.append("优先级不正确（issue.priority）")
    try:
        check_citations(engine, issue.get("citations"), refs, allowed)
    except ValueError as exc:
        errors.append(f"问题引文（issue.citations）：{exc}")
    return errors


def prepare_citations(engine, row, refs, allowed):
    entry = dict(row)
    issue = entry.get("issue")
    has_issue = entry.get("decision") != "排除" and isinstance(issue, dict)
    fields = {"evidence": entry.get("evidence")}
    if has_issue:
        issue = dict(issue)
        entry["issue"] = issue
        fields["issue.citations"] = issue.get("citations")
        for key, other in (("evidence","issue.citations"), ("issue.citations","evidence")):
            if fields[key] is None or fields[key] == []:
                fields[key] = fields[other]
    changes = []
    checked = {}
    for key, values in fields.items():
        checked[key], events = engine["QUOTE"]["resolve"](values, refs, allowed, engine["LOC"]["display_location"])
        for e in events:
            # 同一摘句常在 evidence 和 issue.citations 镜像出现，保留两个位置。
            previous = next((old for old in changes if key not in old["fields"] and
                            all(old.get(k) == v for k, v in e.items())), None)
            if previous is None:
                changes.append(dict(e, fields=[key]))
            else:
                previous["fields"].append(key)
    entry["evidence"] = checked["evidence"]
    if has_issue:
        issue["citations"] = checked["issue.citations"] or entry["evidence"]
        if not entry["evidence"] and issue["citations"]:
            entry["evidence"] = issue["citations"]
    return entry, changes


def review_with_pending(engine, validate, obj, group, refs, allowed, citation_audit=None, ignored_ids=None):
    entries = obj.get("reviews") if isinstance(obj, dict) else None
    if not isinstance(entries, list):
        raise ValueError("模型未返回全篇回查列表。")
    candidates = {candidate["candidateId"]: candidate for candidate in group}
    seen = set()
    retained, audit = [], []
    for row in entries:
        ids = row.get("candidateIds") if isinstance(row, dict) else None
        if not isinstance(ids, list) or not ids or any(not isinstance(cid, str) for cid in ids):
            raise ValueError("全篇回查的候选编号缺失、重复或不匹配。")
        if ignored_ids is not None:
            ignored_ids.extend(cid for cid in ids if cid not in candidates)
        ids = [cid for cid in ids if cid in candidates]
        if not ids:
            continue
        if len(set(ids)) != len(ids) or any(cid in seen for cid in ids):
            raise ValueError("全篇回查的候选编号缺失、重复或不匹配。")
        row = dict(row, candidateIds=ids)
        seen.update(ids)
        entry, changes = prepare_citations(engine, row, refs, allowed)
        errors = review_errors(entry, refs, allowed, engine)
        partial = any(e["action"] == "移除" for e in changes)
        if not errors and entry.get("decision") == "排除" and partial and entry["evidence"]:
            entry.update(decision="待核", reason=engine["QUOTE"]["PARTIAL_REASON"])
            for cid in ids:
                item = engine["QUOTE"]["annotate"](dict(candidates[cid], candidateIds=[cid], bucket="pending"), changes)
                retained.append(item)
                audit.append(dict(candidateIds=[cid], decision="待核", reason=entry["reason"], evidence=entry["evidence"],
                                  rawReply=json.dumps(row,ensure_ascii=False)[:1600]))
            if citation_audit is not None:
                citation_audit.extend(dict(e,candidateIds=ids) for e in engine["QUOTE"]["audit_rows"](changes,"回查",candidates[ids[0]]["title"],True))
            continue
        if citation_audit is not None:
            title = candidates[ids[0]].get("title","")
            citation_audit.extend(dict(e,candidateIds=ids) for e in engine["QUOTE"]["audit_rows"](changes,"回查",title,not errors,"；".join(errors)))
        if not errors:
            results, decisions = validate({"reviews": [entry]}, [candidates[cid] for cid in ids], refs, allowed)
            for item in results:
                engine["QUOTE"]["annotate"](item, changes, [candidates[cid] for cid in ids])
                item["bucket"] = engine["issue_bucket"](item)
                if item.get("partialCitations"):
                    decisions[0].update(decision="待核",reason=item["checkReason"])
            retained.extend(results)
            if changes:
                decisions[0]["rawReply"] = json.dumps(row,ensure_ascii=False)[:1600]
            audit.extend(decisions)
            continue
        # 初审条目已核验引用，原样保留待人工核对。这里只记录回查错误。
        warning = "回查引文未能对应原文，保留初审结论待人工核对" if any("引用" in e or "引文" in e or "evidence" in e for e in errors) else "回查待核：" + "；".join(errors)
        for cid in ids:
            candidate = candidates[cid]
            retained.append(engine["QUOTE"]["annotate"]({**candidate, "candidateIds": [cid], "aiReview": "待核", "bucket": "pending",
                             "checkReason": warning, "reviewValidationError": True}))
            audit.append({"candidateIds": [cid], "decision": "待核", "reason": warning,
                          "rawReply": json.dumps(row,ensure_ascii=False)[:1600], "errors": errors, "evidence": candidate["citations"]})
    if seen != set(candidates):
        raise ValueError("全篇回查漏处理了部分候选，已保留待核条目。")
    return retained, audit


def install(engine):
    scope = engine["model"].__globals__
    schemas = stage_schemas(engine["CATEGORIES"], engine["PRIORITIES"])
    top_level = "\n输出的最外层必须是 JSON 对象，以 { 开头、以 } 结尾。不要直接返回数组或 Markdown。"
    prompts = {
        "SYSTEM": top_level + "\n顶层必须包含 issues、parameters、focusResults 三个数组；没有内容的数组填 []。",
        "REVIEW_SYSTEM": top_level + (
            "\n顶层只放 reviews 数组。每条都要填写 candidateIds、decision、reason 和非空 evidence。"
            "\n保留和待核时，issue 必须完整填写 category、priority、priorityReason、title、description、suggestion、citations。"
            "description 写完整判断，suggestion 给出完整修改或核对动作。"
            "\nissue.citations 与 evidence 共用依据时，直接复制相同的引用对象。"
            "引用的 source、paragraph 和 quote 必须对应本次输入，quote 从一个段落逐字复制，不得改写或拼接。"
            "\n排除时 issue 填 null，evidence 继续提供支持排除的逐字依据。"
        ),
        "FINAL_SYSTEM": top_level + (
            "\n顶层必须包含 mergeGroups、issues、parameters、focusResults 四个数组，没有内容的数组填 []。"
            "回查记录中标有 reviewValidationError 的待核问题须保留原条目，不参与合并。"
        ),
    }
    for name, guidance in prompts.items():
        engine[name] = scope[name] = scope[name] + guidance
    engine["prepare_review_request"] = lambda cfg, body, phase: configure_qwen_request(cfg, body, phase, schemas)
