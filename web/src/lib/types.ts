// Shape of cartograf's output file (see README "Read the output").
// Every field the analysis may leave out is optional: the UI must not assume it.

export type LinkStatus = 'resolved' | 'managed' | 'unresolved' | 'range' | 'snapshot'
export type LinkType = 'parent' | 'bom' | 'dependency' | 'plugin' | 'inherited'
export type RepoKind = 'framework' | 'linked' | 'adhoc' | 'non-maven' | 'gone'

export interface FrameworkLink {
  framework: string
  artifact: string
  type: LinkType | string
  pom: string
  declared: string | null
  resolved: string | null
  status: LinkStatus | string
  framework_latest?: string | null
  behind?: boolean
  managed_by?: string
  via?: string
  inherited_type?: string
  reason?: string
}

export interface PomCoords {
  groupId?: string | null
  artifactId?: string | null
  version?: string | null
}

export interface PomFacts extends PomCoords {
  path: string
  error?: string
  packaging?: string
  parent?: PomCoords & { relativePath?: string | null }
  [key: string]: unknown
}

export interface Branch {
  sha?: string
  committed_at?: string
  default?: boolean
  maven?: boolean
  kind?: string
  poms?: PomFacts[]
  framework_links?: FrameworkLink[]
  fetch_error?: string
  /** set when the fetch failed: the facts come from this older commit */
  facts_sha?: string
}

export interface Repo {
  project_id?: number
  name?: string
  web_url?: string
  default_branch?: string | null
  status?: 'active' | 'gone' | string
  gone_since?: string
  kind?: RepoKind | string
  latest_tag?: string | null
  uses?: Record<string, Record<string, string[]>>
  branches?: Record<string, Branch>
  inventory_error?: string
  empty_repo?: boolean
}

export interface Framework {
  project_id?: number
  status?: string
  branches?: Record<string, { sha?: string; version?: string | null }>
  artifacts?: string[]
  version_default_branch?: string | null
  latest_tag?: string | null
  latest?: string | null
  used_by?: string[]
  links_to?: string[]
}

export interface ReviewItem {
  type: string
  [key: string]: unknown
}

export interface LastRun {
  projects?: number
  branches?: number
  fetched?: number
  reused?: number
  fetch_errors?: number
  gone?: number
  missing_groups?: string[]
  api_requests?: number
}

export interface Meta {
  generated_at?: string
  gitlab_url?: string
  suffix?: string
  groups?: string[]
  branch_window_days?: number
  token_user?: string
  counts?: Record<string, number>
  review_counts?: Record<string, number>
  last_run?: LastRun
  [key: string]: unknown
}

export interface Cartography {
  meta: Meta
  frameworks: Record<string, Framework>
  repos: Record<string, Repo>
  review: ReviewItem[]
}
