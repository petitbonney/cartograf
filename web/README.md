# cartograf web UI

A static page for exploring cartograf's output file. Built with Vite, Svelte 5 and TypeScript; the only runtime dependency is `js-yaml`.

- **Overview**: counts, repositories by kind, framework health, review summary, last-run stats.
- **Frameworks**: latest version and the versions in use, with how many repositories are on each.
- **Repositories**: filter by path, group, kind, framework and version health. Each repository has a detail page with every framework link (declared → resolved, via / managed by, reason) and links to GitLab.
- **Matrix**: repositories × frameworks, coloured by version health. `≠` marks a branch that uses other versions.
- **Review**: the review queue grouped by type, most useful first.

Filters live in the URL (`#/repos?fw=platform/acme-framework&health=behind`), so a view can be shared as a link.

Version health compares each framework link with the framework's latest version: up to date, behind, unresolved (no version found), or not comparable (ranges, or versions that can't be ordered).

## Data

The page loads data in this order:

1. `cartography.yaml`, then `cartography.json`, next to `index.html` (publish them with the site).
2. A file chosen with **Open file…** or dropped anywhere on the page. It is read in the browser and not uploaded.
3. **Try the sample data** loads [public/sample.yaml](public/sample.yaml): fictional repositories, produced by running the real crawl and analysis against a fake GitLab.

To regenerate the sample after a change to the analysis, run this from the repository root (bash). Behind a proxy or a PyPI mirror, add the same certificate and index options that [run-in-docker.sh](../run-in-docker.sh) uses:

```bash
docker run --rm -v "$PWD":/w -w /w python:3.13-slim sh -c 'pip install -q -r requirements.txt -r requirements-dev.txt && python web/scripts/make_sample.py'
```

## Develop

Node 22 or later (bash or fish):

```bash
cd web
```

```bash
npm ci
```

```bash
npm run dev
```

To test with a real file, copy it to `web/public/cartography.yaml`. That path is git-ignored so it can't be committed by accident.

Checks, as in CI:

```bash
npm run check
```

```bash
npm test
```

```bash
npm run build
```

`npm run build` writes `web/dist/`. Asset paths are relative (`base: './'`) and routing uses the URL hash, so the build works from any subpath with no server configuration.

## Publish

**GitHub Pages**: [.github/workflows/pages.yml](../.github/workflows/pages.yml) builds and deploys on every push to `main` that touches `web/`. Turn it on once under *Settings → Pages → Source: GitHub Actions*. GitHub Pages sites are public, so this publishes only the UI and the sample. People open their own file in the page.

**GitLab Pages**: [.gitlab-ci.yml](../.gitlab-ci.yml) does the same on the default branch, and type-checks and tests merge requests. To publish your data with the site, commit `cartography.yaml` at the repository root and set the CI/CD variable `CARTOGRAF_PUBLISH_DATA=true`. Only do this with Pages access control on. Behind a TLS-intercepting proxy, set `NODE_EXTRA_CA_CERTS` as a CI/CD *file* variable with your CA certificate so `npm ci` can reach the registry.
