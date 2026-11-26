"""Analysis: a pure function over the stored facts (no network).

Reads `state["repos"]` (inventory + parsed pom facts) and (re)computes every
derived field: repo/branch kinds, framework links, the `frameworks` section,
the `review` list and `meta.counts`.
"""

from __future__ import annotations

import json
from collections import defaultdict

from .resolver import (
    PomRef,
    Resolver,
    compare_versions,
    ga,
    version_status,
)

LINK_TYPES = ("parent", "bom", "dependency", "plugin")


def is_framework(repo_path: str, repo: dict, suffix: str) -> bool:
    slug = repo_path.rsplit("/", 1)[-1]
    return slug.endswith(suffix) or (repo.get("name") or "").endswith(suffix)


def root_pom(poms: list[dict]) -> dict | None:
    ok = [p for p in poms if "error" not in p]
    if not ok:
        return None
    for p in ok:
        if p["path"] == "pom.xml":
            return p
    return min(ok, key=lambda p: (p["path"].count("/"), p["path"]))


def analyze(state: dict) -> dict:
    meta = state.setdefault("meta", {})
    suffix = meta["suffix"]
    repos: dict = state.setdefault("repos", {})
    review: list[dict] = []

    fw_paths = {path for path, r in repos.items() if is_framework(path, r, suffix)}

    # -- pom index over everything we know (gone repos included: their artifacts still exist)
    refs: list[PomRef] = []
    refs_by_checkout: dict[tuple[str, str], list[PomRef]] = {}
    for path, r in sorted(repos.items()):
        for bname, b in sorted((r.get("branches") or {}).items()):
            lst = []
            for facts in b.get("poms") or []:
                if "error" in facts:
                    continue
                ref = PomRef(r["project_id"], path, bname, bool(b.get("default")), facts)
                refs.append(ref)
                lst.append(ref)
            refs_by_checkout[(path, bname)] = lst
    res = Resolver(refs)

    # -- framework artifacts
    owner: dict[str, str] = {}
    collisions: dict[str, set[str]] = defaultdict(set)
    for fw in sorted(fw_paths):
        for bname in sorted(repos[fw].get("branches") or {}):
            for ref in refs_by_checkout.get((fw, bname), []):
                a = ref.ga
                if a in owner and owner[a] != fw:
                    collisions[a].update({owner[a], fw})
                owner.setdefault(a, fw)
    for a, fws in sorted(collisions.items()):
        review.append({"type": "artifact_collision", "artifact": a, "frameworks": sorted(fws),
                       "detail": f"attributed to {owner[a]}"})

    # -- frameworks section
    frameworks: dict[str, dict] = {}
    for fw in sorted(fw_paths):
        r = repos[fw]
        branches = {}
        default_version = None
        for bname, b in sorted((r.get("branches") or {}).items()):
            rp = root_pom(b.get("poms") or [])
            v = None
            if rp is not None:
                v = res.effective_version(PomRef(r["project_id"], fw, bname, bool(b.get("default")), rp))
            branches[bname] = {"sha": b.get("sha"), "version": v}
            if b.get("default"):
                default_version = v
        latest_tag = r.get("latest_tag")
        reference = latest_tag or default_version
        frameworks[fw] = {
            "project_id": r["project_id"],
            "status": r.get("status", "active"),
            "branches": branches,
            "artifacts": sorted(a for a, o in owner.items() if o == fw),
            "version_default_branch": default_version,
            "latest_tag": latest_tag,
            "latest": reference,
            "used_by": [],
            "links_to": [],
        }
        if not any(b.get("maven") for b in (r.get("branches") or {}).values()):
            review.append({"type": "framework_without_pom", "repo": fw,
                           "detail": "repo name ends with the suffix but no pom.xml was found"})

    # -- per repo / branch
    unresolved_parents: dict[str, dict] = {}
    version_gaps: dict[str, dict] = {}
    counts = defaultdict(int)

    for path, r in sorted(repos.items()):
        if r.get("status") == "gone":
            r["kind"] = "gone"
            r.pop("uses", None)
            counts["gone"] += 1
            continue
        counts["repos_seen"] += 1
        is_fw = path in fw_paths
        any_maven = False
        any_link = False
        any_unknown = False
        if r.get("inventory_error"):
            review.append({"type": "inventory_error", "repo": path, "detail": r["inventory_error"]})
        uses: dict[str, dict[str, list[str]]] = defaultdict(dict)

        for bname, b in sorted((r.get("branches") or {}).items()):
            if b.get("fetch_error"):
                item = {"type": "fetch_error", "repo": path, "branch": bname, "detail": b["fetch_error"]}
                if b.get("facts_sha"):
                    item["facts_sha"] = b["facts_sha"]  # analysis uses the facts of this older commit
                review.append(item)
            poms = b.get("poms") or []
            for p in poms:
                if "error" in p:
                    review.append({"type": "pom_error", "repo": path, "branch": bname,
                                   "pom": p["path"], "detail": p["error"]})
            if "maven" not in b:  # never read: the fetch failed and there are no earlier facts
                b["kind"] = "unknown"
                b.pop("framework_links", None)
                any_unknown = True
                continue
            if not b["maven"]:
                b["kind"] = "non-maven"
                b.pop("framework_links", None)
                continue
            any_maven = True
            links: list[dict] = []
            for ref in refs_by_checkout.get((path, bname), []):
                links.extend(_links_for_pom(ref, res, owner, frameworks, path))
                _collect_parent_problems(ref, res, unresolved_parents, version_gaps)
                if not is_fw:
                    w = _weak_signals(ref, owner, suffix)
                    if w:
                        review.append({"type": "weak_signal", "repo": path, "branch": bname,
                                       "pom": ref.path, "detail": w})
            links = _dedup_sorted(links)
            for lk in links:
                if lk["status"] in ("unresolved", "range", "snapshot"):
                    item = {"type": f"{lk['status']}_version", "repo": path, "branch": bname,
                            "pom": lk["pom"], "artifact": lk["artifact"],
                            "declared": lk.get("declared"), "link_type": lk["type"]}
                    if lk.get("reason"):
                        item["detail"] = lk["reason"]
                    if lk["status"] != "unresolved":
                        item["resolved"] = lk["resolved"]
                    review.append(item)
                uses[lk["framework"]].setdefault(bname, [])
                v = lk["resolved"] if lk["resolved"] is not None else "unresolved"
                if v not in uses[lk["framework"]][bname]:
                    uses[lk["framework"]][bname].append(v)
            b["framework_links"] = links
            if links:
                any_link = True
                b["kind"] = "framework" if is_fw else "linked"
            else:
                b["kind"] = "framework" if is_fw else "adhoc"

        # repo-level summary
        uses_sorted = {fw: {br: sorted(vs) for br, vs in sorted(m.items())} for fw, m in sorted(uses.items())}
        if uses_sorted:
            r["uses"] = uses_sorted
        else:
            r.pop("uses", None)
        for fw, per_branch in uses_sorted.items():
            if len(per_branch) > 1 and len({tuple(v) for v in per_branch.values()}) > 1:
                review.append({"type": "branch_disagreement", "repo": path, "framework": fw,
                               "versions": per_branch})
            if fw in frameworks:
                frameworks[fw]["used_by"].append(path)
            if is_fw:
                frameworks[path]["links_to"].append(fw)

        if is_fw:
            r["kind"] = "framework"
            counts["frameworks"] += 1
        elif any_link:
            r["kind"] = "linked"
            counts["linked"] += 1
        elif any_maven:
            r["kind"] = "adhoc"
            counts["adhoc"] += 1
        elif any_unknown or (r.get("inventory_error") and not r.get("branches")):
            r["kind"] = "unknown"
            counts["unknown"] += 1
        else:
            r["kind"] = "non-maven"
            counts["non_maven"] += 1
        if any_maven:
            counts["maven"] += 1

    for fw in frameworks.values():
        fw["used_by"] = sorted(set(fw["used_by"]))
        fw["links_to"] = sorted(set(fw["links_to"]))
        if not fw["links_to"]:
            del fw["links_to"]

    for key, item in sorted(unresolved_parents.items()):
        item["poms"] = sorted(item["poms"])
        item["versions"] = sorted(item["versions"])
        item["count"] = len(item["poms"])
        review.append(item)
    for key, item in sorted(version_gaps.items()):
        item["poms"] = sorted(item["poms"])
        item["count"] = len(item["poms"])
        review.append(item)

    review.sort(key=lambda x: (x["type"], json.dumps(x, sort_keys=True)))
    state["frameworks"] = frameworks
    state["review"] = review
    review_counts: dict[str, int] = defaultdict(int)
    for item in review:
        review_counts[item["type"]] += 1
    meta["counts"] = {
        k: counts[k]
        for k in ("repos_seen", "maven", "non_maven", "unknown", "frameworks", "linked", "adhoc", "gone")
    }
    meta["review_counts"] = dict(sorted(review_counts.items()))
    return state


# -- link detection ------------------------------------------------------------


def _links_for_pom(ref: PomRef, res: Resolver, owner: dict, frameworks: dict, repo: str) -> list[dict]:
    links = _direct_links(ref, ref, res, owner, frameworks, exclude={repo})
    # Inherited links: only where the immediate parent lives in another repo
    # (modules of the same repo are covered by their in-repo parent's own links).
    chain, _ = res.chain(ref)
    if len(chain) > 1 and chain[1].repo != ref.repo:
        for anc in chain[1:]:
            for lk in _direct_links(anc, ref, res, owner, frameworks, exclude={repo, anc.repo}):
                lk["inherited_type"] = lk["type"]
                lk["type"] = "inherited"
                lk["via"] = f"{res.coords(anc)} ({anc.where()})"
                lk["pom"] = ref.path
                links.append(lk)
    return links


def _direct_links(decl: PomRef, ctx: PomRef, res: Resolver, owner: dict, frameworks: dict,
                  exclude: set[str]) -> list[dict]:
    """Framework links declared in `decl`, versions resolved in the context of `ctx`."""
    f = decl.facts
    out: list[dict] = []

    def add(kind: str, group, artifact, declared, resolved, missing, managed=None, reason=None):
        a = ga(group, artifact)
        fw = owner.get(a)
        if fw is None or fw in exclude:
            return
        status = version_status(resolved, managed is not None)
        lk = {
            "framework": fw,
            "artifact": a,
            "type": kind,
            "pom": decl.path,
            "declared": declared,
            "resolved": resolved,
            "status": status,
        }
        if managed:
            lk["managed_by"] = managed
        if resolved is None:
            lk["reason"] = reason or (
                f"undefined properties: {', '.join(missing)}" if missing else "no version declared"
            )
        latest = frameworks.get(fw, {}).get("latest")
        lk["framework_latest"] = latest
        if resolved is not None and latest and status in ("resolved", "managed", "snapshot"):
            cmp = compare_versions(resolved, latest)
            if cmp is not None:
                lk["behind"] = cmp < 0
        out.append(lk)

    par = f.get("parent")
    if par:
        v, miss = res.resolve(par.get("version"), decl, own_only=True)
        add("parent", par.get("groupId"), par.get("artifactId"), par.get("version"), v, miss)

    for d in f.get("dependencyManagement", []):
        if d.get("scope") == "import":
            v, miss = res.resolve(d.get("version"), ctx)
            add("bom", d.get("groupId"), d.get("artifactId"), d.get("version"), v, miss)

    for d in f.get("dependencies", []):
        g, a = d.get("groupId"), d.get("artifactId")
        if owner.get(ga(g, a)) in (None, *exclude):
            continue
        if d.get("version"):
            v, miss = res.resolve(d["version"], ctx)
            add("dependency", g, a, d["version"], v, miss)
        else:
            m = res.managed_dependency(ctx, g, a)
            if m["found"]:
                add("dependency", g, a, m["declared"], m["resolved"], m["missing"], managed=m["managed_by"])
            else:
                add("dependency", g, a, None, None, [], reason=m["reason"])

    for p in f.get("plugins", []) + f.get("pluginManagement", []):
        g, a = p.get("groupId"), p.get("artifactId")
        if owner.get(ga(g, a)) in (None, *exclude):
            continue
        if p.get("version"):
            v, miss = res.resolve(p["version"], ctx)
            add("plugin", g, a, p["version"], v, miss)
        else:
            m = res.managed_plugin(ctx, g, a)
            if m["found"]:
                add("plugin", g, a, m["declared"], m["resolved"], m["missing"], managed=m["managed_by"])
            else:
                add("plugin", g, a, None, None, [], reason=m["reason"])
    return out


def _dedup_sorted(links: list[dict]) -> list[dict]:
    seen = {}
    for lk in links:
        k = json.dumps(lk, sort_keys=True)
        seen.setdefault(k, lk)
    return sorted(seen.values(), key=lambda lk: (lk["framework"], lk["pom"], lk["type"], lk["artifact"],
                                                 json.dumps(lk, sort_keys=True)))


def _collect_parent_problems(ref: PomRef, res: Resolver, unresolved: dict, gaps: dict) -> None:
    _, problem = res.parent(ref)
    if not problem:
        return
    if problem["type"] == "unresolved_parent":
        key = problem["parent"]
        item = unresolved.setdefault(key, {"type": "unresolved_parent", "parent": key,
                                           "versions": set(), "poms": [],
                                           "detail": "parent not found in the crawl (external, e.g. Nexus)"})
        if problem.get("version"):
            item["versions"].add(problem["version"])
        item["poms"].append(ref.where())
    elif problem["type"] == "parent_version_not_in_crawl":
        key = problem["parent"]
        item = gaps.setdefault(key, {"type": "parent_version_not_in_crawl", "parent": key, "poms": [],
                                     "available": problem.get("available", []),
                                     "detail": problem.get("reason")
                                     or "parent coordinates are in the crawl but not at this version; "
                                        "inherited properties/management from it are not used"})
        item["poms"].append(ref.where())
    else:
        key = f"{problem['type']}:{ref.where()}"
        gaps.setdefault(key, {"type": problem["type"], "poms": [ref.where()]})


def _weak_signals(ref: PomRef, owner: dict, suffix: str) -> list[str]:
    s = suffix.lower()
    f = ref.facts
    hits: list[str] = []

    def check(label: str, g, a):
        coord = ga(g, a)
        if s in coord.lower() and coord not in owner:
            hits.append(f"{label} {coord}")

    check("own", f.get("groupId"), f.get("artifactId"))
    par = f.get("parent")
    if par:
        check("parent", par.get("groupId"), par.get("artifactId"))
    for d in f.get("dependencyManagement", []) + f.get("dependencies", []):
        check("dependency", d.get("groupId"), d.get("artifactId"))
    for p in f.get("plugins", []) + f.get("pluginManagement", []):
        check("plugin", p.get("groupId"), p.get("artifactId"))
    for u in f.get("urls", []):
        if s in u.lower():
            hits.append(f"url {u}")
    return sorted(set(hits))
