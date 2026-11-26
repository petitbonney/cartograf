# PLAN: GitLab Maven framework cartography

Plan for a later implementation session. Nothing is implemented yet. All decisions below were agreed with the user; open items are listed at the end.

## 1. Goal

Build a **cartography of Maven dependencies across GitLab repositories, focused on "framework" repos**.

- Some central repos ("frameworks") share a **common suffix in the repository name**.
- We do not know which sub-repos use which framework.
- Input: the suffix + a list of GitLab groups (same GitLab instance).
- Output: for every repo, whether it is a framework, a sub-repo linked to one or more frameworks (with the **framework version it uses**), an ad hoc repo (no framework), or not a Maven repo.

## 2. Decisions already made

| Topic | Decision |
|---|---|
| Where it runs | **Local script run by a human** who has access to all target repos (not a GitLab CI job). |
| Language | **Python**. |
| Auth | **Personal access token** from env `GITLAB_TOKEN`, scope `read_api` (add `read_repository` only if cloning is ever used). Instance URL from env `GITLAB_URL` or a CLI arg. Never write the token to the output file or logs. |
| Framework identification | A repo is a framework if **its name ends with the suffix**. The suffix is *only* in the repo name, not in artifactIds. |
| Link detection | Match on **Maven coordinates** (`groupId:artifactId`) published by framework repos, not on text search for the suffix. |
| Scope of analysis | Static parsing of `pom.xml`. No `mvn` execution, no transitive resolution. |
| Re-runnable | Yes, **incremental**: only reprocess repos whose branch head SHA changed since the last run. |
| Branches | Default branch + the **most recently committed branch** (within an age window, default 90 days, bot branches excluded). No branch convention exists. |
| Output | **A single YAML file** that is also the incremental state. Optionally `--format json`. |
| Scale | Hundreds of repos. Number of Maven repos unknown; non-Maven repos must be detected and ignored. |

## 3. Algorithm

### 3.1 Pass 0: inventory
1. For each group in the config: `GET /groups/:id/projects?include_subgroups=true&archived=false&per_page=100`, following pagination (`x-next-page`). Group may be an ID or a URL-encoded path.
2. Deduplicate projects by ID (groups may overlap).
3. For each project, `GET /projects/:id/repository/branches` (paginated) to get each branch's head SHA and commit date. Skip empty repos (no branches).

### 3.2 Branch selection (per repo)
- Always: the default branch.
- Also: the branch with the most recent commit, if different from default, newer than `--branch-window-days` (default 90), and not matching excluded patterns (default: `dependabot/*`, `renovate/*`, `renovate-*`, plus configurable).
- Each selected branch is analyzed and stored separately. Report disagreements (see 3.6).

### 3.3 Incremental skip
For each (project, branch), compare the head SHA with the stored one in the existing YAML. Unchanged: reuse the stored facts and skip fetching. Changed or new: re-fetch. Repos that disappeared (deleted, archived, renamed, no longer in groups): mark `status: gone`, do not silently drop. A `--full` flag ignores stored SHAs.

### 3.4 Fetch (per repo/branch that changed)
1. `GET /projects/:id/repository/tree?recursive=true&ref=<sha>&per_page=100` (paginated). Collect every `pom.xml` path (multi-module repos have many).
2. No `pom.xml` found: record `kind: non-maven` with the head SHA, so it is not re-inspected until it gets a new commit.
3. Otherwise download each pom via `GET /projects/:id/repository/files/:path/raw?ref=<sha>` (URL-encode the path). Use bounded parallelism (thread pool, default ~8) with 429/5xx retry and backoff honoring `Retry-After`.
4. Parse each pom with `xml.etree` / `defusedxml`; handle the Maven namespace. Extract and **store the parsed facts in the YAML, not the raw XML**:
   - own `groupId`, `artifactId`, `version` (inherit groupId/version from `<parent>` if absent), `packaging`
   - `<parent>` coordinates
   - `<properties>`
   - `<dependencyManagement>` entries, including BOM imports (`scope=import`, `type=pom`)
   - `<dependencies>` (groupId, artifactId, version expression, scope)
   - plugins and `pluginManagement` (groupId, artifactId, version expression)
   - the pom path within the repo

### 3.5 Analysis (pure function over stored facts, no network)
1. **Frameworks**: all repos whose name ends with the suffix. Their published artifacts are the set of `groupId:artifactId` from their poms (root + modules), and their current version(s).
2. **Parent chain resolution**: for each pom, resolve `<parent>` against poms known in the crawl (match by coordinates). Build the chain upward. Unresolvable parents (outside the crawl, e.g. corporate parent in Nexus) are recorded as `unresolved_parent` in `review`. It is unknown whether an intermediate corporate parent exists; the first run will reveal it. Make this visible, not guessed.
3. **Property resolution**: resolve `${...}` using the pom's own properties, then up the resolved parent chain; also `${project.version}`, `${project.parent.version}`, `${project.groupId}`.
4. **Link detection** per non-framework pom, against the framework artifact set:
   - `parent` (pom's parent is a framework artifact)
   - `bom` (import-scope dependencyManagement)
   - `dependency`
   - `plugin`
   - Inherited links via an intermediate parent in the crawl count as `inherited` (record via which parent).
5. **Version per link**: record `declared` (raw expression), `resolved` (string or null), and `status` in `{resolved, unresolved, range, snapshot, managed}`. If the version is absent and managed by a BOM/parent, resolve through `dependencyManagement` up the chain. **Never guess**: unresolved stays `null` with a reason.
6. **Classification** per repo (per branch, then a repo-level summary):
   - `framework`: name ends with suffix (it may *also* link to other frameworks; record that)
   - `linked`: at least one framework link (a repo can link to several frameworks)
   - `adhoc`: Maven repo with zero framework links
   - `non-maven`: no pom.xml
7. **Latest framework version** for comparison: the framework's own pom version on its analyzed branches (and optionally its latest semver tag via `/repository/tags`). Add `behind` info to each link where comparable.

### 3.6 Review section (flagged, not auto-decided)
- Unresolved parents and unresolved versions
- Range/SNAPSHOT versions
- **Branch disagreements**: same repo, different framework version on default vs most-recent branch
- Weak signals: a `groupId`/`artifactId` containing the suffix, or the framework repo name appearing in `<scm>`/`<url>`, that did not match a known framework (could be frameworks outside the crawl or naming drift)
- Repos with a pom.xml but in an odd state (parse errors, empty files)

## 4. Output file (YAML)

Single file, default `cartography.yaml`. Deterministic output: sorted keys and sorted lists, so it diffs cleanly in git.

**Critical YAML pitfall**: force all versions (and anything version-like or `yes/no/on/off`-like) to be **quoted strings**. Use a safe dumper and `safe_load`, no custom tags. Test this explicitly (`3.10`, `1.0`, `no`).

```yaml
meta:
  generated_at: "2026-11-25T15:30:00+01:00"
  gitlab_url: "https://gitlab.example.com"
  suffix: "-framework"
  groups: ["grp-a", "grp-b"]
  branch_window_days: 90
  counts: {repos_seen: 0, maven: 0, non_maven: 0, frameworks: 0, linked: 0, adhoc: 0}
frameworks:
  <repo path>:
    project_id: 123
    branches: {<branch>: {sha: "...", version: "..."}}
    artifacts: ["group:artifact", ...]
repos:
  <repo path>:
    project_id: 456
    kind: linked        # framework | linked | adhoc | non-maven | gone
    branches:
      <branch>:
        sha: "..."
        committed_at: "..."
        poms:           # parsed facts per pom path (see 3.4)
        framework_links:
          - framework: <repo path>
            artifact: "group:artifact"
            type: parent|bom|dependency|plugin|inherited
            pom: "path/pom.xml"
            declared: "${fw.version}"
            resolved: "3.2.1"
            status: resolved
            framework_latest: "3.5.0"
review:
  - {type: unresolved_parent, repo: ..., detail: ...}
```

Stored parsed pom facts keep the file self-sufficient so analysis (3.5) can be re-run for unchanged repos when rules or the framework set change. Keep the file size reasonable (store only needed fields). If it gets too big, discuss moving pom facts to a sidecar cache.

## 5. CLI

```
cartography.py --suffix=-framework --groups grp-a,grp-b [--groups-file groups.txt]
               [--url https://gitlab.example.com]   # else $GITLAB_URL
               [--output cartography.yaml] [--format yaml|json]
               [--branch-window-days 90] [--exclude-branch PATTERN ...]
               [--workers 8] [--full] [--analyze-only] [--verbose]
```
- `--analyze-only`: no network; re-run analysis (3.5) from the stored facts.
- Print a final summary (counts, number fetched vs skipped, review items).
- Fail clearly if `GITLAB_TOKEN` is missing or the token is rejected (401), and list groups that are not found or not accessible (404).

## 6. Suggested code structure

Single package or a few modules, keep it simple:
- `gitlab_client.py`: auth, pagination, retry/backoff, URL encoding, bounded concurrency
- `pom_parser.py`: namespace-safe parsing into plain dicts
- `resolver.py`: property resolution, parent chain, dependencyManagement/BOM resolution
- `analyze.py`: framework set, link detection, classification, review list
- `store.py`: load/save YAML (deterministic, quoted versions), state merge
- `cartography.py`: CLI glue
- `tests/`: pytest with **fixture poms** (no network): property resolution, parent inheritance, BOM-managed versions, multi-module, range/SNAPSHOT, unresolved parent, non-Maven repo, YAML quoting round-trip, incremental skip logic using a mocked client

Dependencies: `requests`, `PyYAML` (or `ruamel.yaml`), `defusedxml`, `pytest`. Python 3.10+.

## 7. Implementation order

1. Client + inventory (pass 0) + branch selection; print what would be fetched.
2. Fetch + pom parsing + store, with incremental skip.
3. Resolver + analysis + review.
4. YAML shape and quoting tests; `--analyze-only`; `--format json`.
5. Real-world dry run on one small group, inspect the `review` list, then widen.
6. README with token creation steps (User settings → Access tokens, scope `read_api`) and example usage.

## 8. Risks / things to watch

- Rate limits on the instance: backoff, modest default concurrency.
- Large repos: the recursive tree call is paginated and can be big; consider skipping `node_modules`-like noise (tree endpoint returns all paths; filter client-side to basename `pom.xml`).
- Poms using `<relativePath>` or parents only available in Nexus: report, don't fail.
- Framework repos may themselves depend on other frameworks (record, show in the graph later).
- Renamed/moved repos change the path but not the project ID: key state by **project ID**, display by path.
- The token acts as the user, so results reflect that user's visibility. Record this in `meta`.
- Do not clone and do not execute any code from the repos: only fetch and parse XML (use `defusedxml` to avoid XML entity attacks).

## 9. Out of scope for now

- Graph rendering (Mermaid/Graphviz/HTML), CSV export. These can be generated from the YAML later.
- Transitive dependency resolution, Gradle repos.
- Scheduled/CI execution.

## 10. Open items to confirm at the start of the implementation session

1. GitLab base URL, the suffix, and the list of groups (will be provided by the user).
2. A folder on the user's computer to write the project into (needs folder access via the desktop app).
3. Whether an intermediate corporate parent pom exists (will be discovered by the first run's `review` section).
4. Preferred default for the age window (90 days proposed) and bot-branch exclusion patterns.
