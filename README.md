# cartograf

Maps Maven framework usage across GitLab repositories.

- A **framework** is a repository whose name ends with a given suffix (e.g. `-framework`).
- Every other repo in the given groups is classified as **linked** (uses at least one framework, with the version it uses), **adhoc** (Maven, no framework), **non-maven**, or **gone** (no longer visible).
- Links are found by Maven coordinates (`groupId:artifactId`) published by the framework repos: `parent`, `bom` (import), `dependency`, `plugin`, and `inherited` (through an intermediate parent pom from another repo, e.g. a corporate parent).
- Static `pom.xml` parsing only, read through the GitLab API. Nothing is cloned or executed, and Maven is not run.
- The output is a single YAML file that also serves as incremental state. On later runs only branches whose head SHA changed are re-fetched.

See [PLAN.md](PLAN.md) for the full design.

## 1. Create a token

GitLab → avatar → **Edit profile → Access tokens → Add new token**, scope **`read_api`**, with a short expiry. The results only show what this token's user can see; the user name is recorded in `meta.token_user`.

## 2. Run (Docker in WSL)

[run-in-docker.sh](run-in-docker.sh) runs the tool in a throwaway `python:3.13-slim` container. Nothing is installed in WSL apart from Docker. The commands below are bash.

Clone the project into the WSL filesystem (e.g. `~/cartograf`), not under `/mnt/c/...`. [.gitattributes](.gitattributes) keeps LF line endings, so the script runs as is.

**Certificate.** Give the path to your CA certificate (PEM, as found in `/usr/local/share/ca-certificates`). The container trusts it on top of the usual public CAs, for both pip and GitLab. Leave `CA_CERT` unset if you don't need one.

```bash
export CA_CERT=/usr/local/share/ca-certificates/corp.crt
```

**PyPI mirror.** If public PyPI is blocked, point pip at your internal index. The script passes both variables into the container when they are set:

```bash
export PIP_INDEX_URL=https://nexus.example.com/repository/pypi/simple
```

```bash
export PIP_TRUSTED_HOST=nexus.example.com
```

**Token and URL.** `read -s` keeps the token out of shell history and off the screen:

```bash
read -rsp 'GitLab token: ' GITLAB_TOKEN; echo; export GITLAB_TOKEN
```

```bash
export GITLAB_URL=https://gitlab.example.com
```

Put the `export` lines (except the token) in `~/.bashrc` to set them once.

First a dry run, which lists what would be fetched and writes nothing:

```bash
./run-in-docker.sh --suffix=-framework --groups grp-a,grp-b --dry-run
```

Then the real run:

```bash
./run-in-docker.sh --suffix=-framework --groups grp-a,grp-b
```

With the wrapper, only the project folder is mounted, so `--output` must point inside it. Later runs can omit `--suffix`, `--groups`, and `--url`. They are read back from `meta` in the existing output file:

```bash
./run-in-docker.sh
```

### Options

| Option | Meaning |
|---|---|
| `--suffix` | repo-name suffix that marks a framework (matched on the repo path slug or display name) |
| `--groups a,b` / `--groups-file f` | group IDs or full paths (subgroups included, archived projects excluded) |
| `--url` | GitLab base URL (else `$GITLAB_URL`) |
| `--output` | default `cartography.yaml` (`cartography.json` with `--format json`) |
| `--format yaml\|json` | output format |
| `--branch-window-days N` | the "most recent branch" must have a commit in the last N days (default 90) |
| `--exclude-branch GLOB` | extra branches to ignore (defaults: `dependabot/*`, `renovate/*`, `renovate-*`) |
| `--exclude-pom-path GLOB` | extra pom paths to ignore (defaults skip `src/test`, `src/it`, `target`, `node_modules`) |
| `--workers N` | concurrent API requests (default 8). Retries 429/5xx with backoff and honors `Retry-After` |
| `--full` | ignore stored SHAs and re-fetch everything |
| `--analyze-only` | no network: re-run the analysis on stored facts, e.g. after changing the suffix |
| `--dry-run` | inventory + branch selection only |
| `--no-tags` | skip reading framework tags (used for the "latest" version) |

Exit codes: `0` ok, `1` GitLab/auth error (including 401 or no accessible group), `2` usage error. Groups that return 404/403 are listed as warnings and in `meta.last_run.missing_groups`.

## 3. Read the output

```yaml
meta:        # run parameters, counts, review_counts, last_run stats
frameworks:  # per framework: artifacts, version per branch, latest_tag, latest, used_by, links_to
repos:       # per repo (keyed by path, matched across runs by project_id)
  grp/svc:
    kind: linked
    uses: {grp/acme-framework: {main: ["3.4.0"]}}
    branches:
      main:
        sha, committed_at, default, maven
        poms: [...]             # parsed pom facts (what the analysis runs on)
        framework_links:
          - framework, artifact, type, pom, declared, resolved, status,
            framework_latest, behind, managed_by | via + inherited_type | reason
review:      # items that need a human look
```

- `status`: `resolved` (explicit version), `managed` (no version, taken from dependencyManagement/pluginManagement of the parent chain or an imported BOM), `unresolved` (`resolved: null` plus a `reason`), `range`, `snapshot`.
- `framework_latest`: the framework's latest release tag if it has one, else its default-branch pom version. `behind` is only set when the two versions are comparable.
- Branches: the default branch, plus the most recently committed other branch inside the window. Each is analyzed separately.

### Review types

| type | meaning |
|---|---|
| `unresolved_parent` | parent not in the crawl (e.g. corporate or Spring parent in Nexus), grouped by parent with the poms using it. **Check this first after the first run**: a recurring corporate parent shows up here. |
| `parent_version_not_in_crawl` | parent coordinates are crawled, but not at that version (typically an older framework version). Managed versions inherited from it stay unresolved. |
| `unresolved_version` / `range_version` / `snapshot_version` | per framework link |
| `branch_disagreement` | default branch and recent branch use different framework versions |
| `weak_signal` | the suffix appears in coordinates or `<url>`/`<scm>` that do not match a known framework (a framework outside the crawl, or naming drift) |
| `pom_error`, `fetch_error` | unparsable/empty pom, or API failure (retried on the next run) |
| `artifact_collision`, `framework_without_pom` | the same artifact is published by two frameworks, or a framework repo has no pom |

## 4. Limitations (by design)

- No transitive resolution, no Gradle, and profiles (`<profiles>`) are not read.
- A parent or BOM from another repo is only used when the exact version is in the crawl (a framework's current branches). Older versions are reported, not guessed.
- Inherited `${project.version}` follows Maven semantics: it is interpolated in the child's context.
- Version comparison approximates Maven ordering for `1.2.3[-qualifier]`. Anything else gives `behind` unset.

## 5. Development

```bash
./run-in-docker.sh --test -q
```

Code map: [gitlab_client.py](cartograf/gitlab_client.py) (HTTP, pagination, retry) · [pom_parser.py](cartograf/pom_parser.py) · [resolver.py](cartograf/resolver.py) (parent chain, properties, management, versions) · [analyze.py](cartograf/analyze.py) (links, classification, review) · [crawl.py](cartograf/crawl.py) (inventory, branch selection, incremental fetch) · [store.py](cartograf/store.py) (deterministic YAML/JSON, always-quoted versions) · [cli.py](cartograf/cli.py).
