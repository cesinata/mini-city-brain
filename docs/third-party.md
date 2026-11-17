# Third-party software

Every dependency, its pinned version and its licence. Python licences come from each package's own metadata (the `License-Expression`, `License` or `Classifier` field of the installed package). Where the metadata does not state a licence, the entry says "not checked". Python package licences were not checked against project web pages; Docker images, Terraform and GitHub Actions were (sections below).

Versions are exact. Python packages were resolved with releases uploaded on or before 2026-10-27, at least 14 days before the build date (2026-11-10). The full pin list is `requirements/constraints.txt`.

## Python packages

Direct dependencies first (marked **direct**), then everything they pull in.

| Package | Version | Licence | Source of the licence | |
| --- | --- | --- | --- | --- |
| boto3 | 1.43.118 | Apache-2.0 | package metadata | **direct** |
| dagster | 1.13.26 | Apache-2.0 | package metadata | **direct** |
| dagster-dbt | 0.29.26 | Apache-2.0 | package metadata | **direct** |
| dagster-webserver | 1.13.26 | Apache-2.0 | package metadata | **direct** |
| dbt-duckdb | 1.11.0 | Apache-2 | package metadata | **direct** |
| duckdb | 2.0.0 | MIT License | package classifier | **direct** |
| fastapi | 0.162.0 | MIT | package metadata | **direct** |
| httpx | 0.28.1 | BSD-3-Clause | package metadata | **direct** |
| jsonschema | 4.26.0 | MIT | package metadata | **direct** |
| moto | 5.2.4 | Apache-2.0 | package metadata | **direct** |
| prometheus_client | 0.26.0 | Apache-2.0 AND BSD-2-Clause | package metadata | **direct** |
| pydantic | 2.14.1 | MIT | package metadata | **direct** |
| pytest | 9.1.1 | MIT | package metadata | **direct** |
| ruff | 0.17.2 | MIT | package metadata | **direct** |
| uvicorn | 0.54.0 | BSD-3-Clause | package metadata | **direct** |
| agate | 1.9.1 | MIT | package metadata |  |
| alembic | 1.20.1 | MIT | package metadata |  |
| annotated-doc | 0.0.5 | MIT | package metadata |  |
| annotated-types | 0.8.0 | MIT | package metadata |  |
| antlr4-python3-runtime | 4.13.2 | BSD | package metadata |  |
| anyio | 4.15.1 | MIT | package metadata |  |
| attrs | 26.1.0 | MIT | package metadata |  |
| aws-xray-sdk | 2.15.0 | Apache License 2.0 | package metadata |  |
| babel | 2.18.0 | BSD-3-Clause | package metadata |  |
| backoff | 2.2.1 | MIT | package metadata |  |
| blinker | 1.9.0 | MIT License | package classifier |  |
| botocore | 1.43.118 | Apache-2.0 | package metadata |  |
| certifi | 2026.10.23 | MPL-2.0 | package metadata |  |
| cffi | 2.1.1 | MIT-0 | package metadata |  |
| cfn-lint | 1.58.0 | MIT-0 | package metadata |  |
| charset-normalizer | 3.5.2 | MIT | package metadata |  |
| click | 8.5.0 | BSD-3-Clause | package metadata |  |
| colorama | 0.4.6 | BSD License | package classifier |  |
| coloredlogs | 14.0 | MIT | package metadata |  |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | package metadata |  |
| daff | 1.4.2 | MIT | package metadata |  |
| dagster-graphql | 1.13.26 | Apache-2.0 | package metadata |  |
| dagster-pipes | 1.13.26 | Apache-2.0 | package metadata |  |
| dagster-shared | 1.13.26 | Apache-2.0 | package metadata |  |
| dbt-adapters | 1.24.5 | Apache Software License | package classifier |  |
| dbt-common | 1.39.0 | Apache-2.0 | package metadata |  |
| dbt-core | 1.12.6 | Apache-2.0 | package metadata |  |
| dbt-core-experimental-parser | 2.0.8 | Apache-2.0 | package metadata |  |
| dbt-extractor | 0.6.0 | Apache-2.0 | package metadata |  |
| dbt-protos | 1.0.615 | Apache-2.0 | package metadata |  |
| deepdiff | 8.6.2 | MIT License | package classifier |  |
| docker | 7.2.0 | Apache-2.0 | package metadata |  |
| docstring_parser | 0.18.0 | MIT | package metadata |  |
| filelock | 4.2.4 | MIT | package metadata |  |
| Flask | 3.1.3 | BSD-3-Clause | package metadata |  |
| flask-cors | 6.0.5 | MIT | package metadata |  |
| fsspec | 2026.9.0 | BSD-3-Clause | package metadata |  |
| gitdb | 4.0.12 | BSD License | package metadata |  |
| GitPython | 3.2.1 | BSD-3-Clause | package metadata |  |
| gql | 4.0.0 | MIT | package metadata |  |
| graphene | 3.4.3 | MIT | package metadata |  |
| graphql-core | 3.2.13 | MIT license | package metadata |  |
| graphql-relay | 3.2.0 | MIT | package metadata |  |
| grpcio | 1.85.0 | Apache-2.0 | package metadata |  |
| grpcio-health-checking | 1.81.1 | Apache-2.0 | package metadata |  |
| h11 | 0.16.0 | MIT | package metadata |  |
| httpcore | 1.0.9 | BSD-3-Clause | package metadata |  |
| httptools | 0.9.0 | MIT | package metadata |  |
| humanfriendly | 10.0 | MIT | package metadata |  |
| idna | 3.20 | BSD-3-Clause | package metadata |  |
| importlib_metadata | 10.1.0 | Apache-2.0 | package metadata |  |
| iniconfig | 2.3.1 | MIT | package metadata |  |
| isodate | 0.7.2 | BSD License | package classifier |  |
| itsdangerous | 2.2.0 | BSD License | package classifier |  |
| Jinja2 | 3.1.6 | BSD License | package classifier |  |
| jmespath | 1.1.0 | MIT | package metadata |  |
| joserfc | 1.7.7 | BSD-3-Clause | package metadata |  |
| jsonpatch | 1.37 | BSD-3-Clause | package metadata |  |
| jsonpath-ng | 1.14.0 | Apache-2.0 | package metadata |  |
| jsonpointer | 3.5 | Modified BSD License | package metadata |  |
| jsonschema-path | 0.5.0 | Apache-2.0 | package metadata |  |
| jsonschema-specifications | 2025.9.1 | MIT | package metadata |  |
| lazy-object-proxy | 1.13.0 | BSD-2-Clause | package metadata |  |
| leather | 0.4.1 | MIT | package metadata |  |
| Mako | 1.4.3 | MIT | package metadata |  |
| markdown-it-py | 4.2.0 | MIT License | package classifier |  |
| MarkupSafe | 3.0.4 | BSD-3-Clause | package metadata |  |
| mashumaro | 3.17 | Apache-2.0 | package metadata |  |
| mdurl | 0.1.2 | MIT License | package classifier |  |
| metricflow | 0.213.0 | Apache-2.0 | package metadata |  |
| more-itertools | 10.8.0 | MIT | package metadata |  |
| mpmath | 1.3.0 | BSD | package metadata |  |
| msgpack | 1.2.3 | Apache-2.0 | package metadata |  |
| multidict | 7.2.1 | Apache-2.0 | package metadata |  |
| networkx | 3.7 | BSD-3-Clause | package metadata |  |
| openapi-schema-validator | 0.9.0 | BSD-3-Clause | package metadata |  |
| openapi-spec-validator | 0.9.0 | Apache-2.0 | package metadata |  |
| opentelemetry-api | 1.45.1 | Apache-2.0 | package metadata |  |
| orderly-set | 5.5.0 | MIT License | package classifier |  |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) | package metadata |  |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | package metadata |  |
| parsedatetime | 2.6 | Apache License 2.0 | package metadata |  |
| pathable | 0.6.0 | Apache-2.0 | package metadata |  |
| pathlib_abc | 0.5.2 | Python Software Foundation License | package classifier |  |
| pathspec | 1.0.4 | Mozilla Public License 2.0 (MPL 2.0) | package classifier |  |
| platformdirs | 4.13.5 | MIT | package metadata |  |
| pluggy | 1.7.0 | MIT | package metadata |  |
| propcache | 0.5.4 | Apache-2.0 | package metadata |  |
| protobuf | 6.33.6 | 3-Clause BSD License | package metadata |  |
| py-partiql-parser | 0.6.3 | MIT | package metadata |  |
| pycparser | 3.12 | BSD-3-Clause | package metadata |  |
| pydantic-settings | 2.16.1 | MIT | package metadata |  |
| pydantic_core | 2.50.1 | MIT | package metadata |  |
| Pygments | 2.21.0 | BSD-2-Clause | package metadata |  |
| pyparsing | 3.3.3 | MIT | package metadata |  |
| python-dateutil | 2.9.0.post0 | Dual License | package metadata |  |
| python-dotenv | 1.2.4 | BSD-3-Clause | package metadata |  |
| python-slugify | 9.1.3 | MIT | package metadata |  |
| pytimeparse | 1.1.10 | License :: OSI Approved :: MIT License | package metadata |  |
| pytz | 2026.5 | MIT | package metadata |  |
| PyYAML | 6.0.3 | MIT | package metadata |  |
| RapidFuzz | 3.14.6 | MIT | package metadata |  |
| referencing | 0.37.0 | MIT | package metadata |  |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python | package metadata |  |
| requests | 2.34.2 | Apache-2.0 | package metadata |  |
| requests-toolbelt | 1.0.0 | Apache 2.0 | package metadata |  |
| responses | 0.26.3 | Apache-2.0 | package metadata |  |
| rfc3339-validator | 0.1.4 | MIT license | package metadata |  |
| rich | 15.0.0 | MIT | package metadata |  |
| rpds-py | 2026.9.1 | MIT | package metadata |  |
| s3transfer | 0.19.3 | Apache License 2.0 | package metadata |  |
| shellingham | 1.5.4 | ISC License | package metadata |  |
| six | 1.17.0 | MIT | package metadata |  |
| smmap | 5.0.3 | BSD-3-Clause | package metadata |  |
| snowplow-tracker | 1.1.0 | Apache License 2.0 | package metadata |  |
| SQLAlchemy | 2.1.6 | MIT | package metadata |  |
| sqlglot | 30.24.0 | MIT | package metadata |  |
| sqlglotc | 30.24.0 | MIT | package metadata |  |
| sqlglotrs | 0.13.0 | MIT | package metadata |  |
| sqlparse | 0.6.0 | BSD License | package classifier |  |
| starlette | 1.10.0 | BSD-3-Clause | package metadata |  |
| structlog | 26.1.0 | MIT OR Apache-2.0 | package metadata |  |
| sympy | 1.14.0 | BSD | package metadata |  |
| tabulate | 0.10.0 | MIT | package metadata |  |
| text-unidecode | 1.3 | Artistic License | package metadata |  |
| tomli | 2.5.0 | MIT | package metadata |  |
| tomlkit | 0.15.2 | MIT | package metadata |  |
| toposort | 1.10 | Apache License Version 2.0 | package metadata |  |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | package metadata |  |
| typer | 0.27.3 | MIT | package metadata |  |
| typing-inspection | 0.4.4 | MIT | package metadata |  |
| typing_extensions | 4.16.0 | PSF-2.0 | package metadata |  |
| tzdata | 2026.5 | Apache-2.0 | package metadata |  |
| universal_pathlib | 0.3.10 | MIT | package metadata |  |
| urllib3 | 2.8.0 | MIT | package metadata |  |
| uvloop | 0.23.0 | MIT License | package metadata |  |
| watchdog | 6.0.0 | Apache-2.0 | package metadata |  |
| watchfiles | 1.3.0 | MIT | package metadata |  |
| websockets | 17.3 | BSD-3-Clause | package metadata |  |
| Werkzeug | 3.1.9 | BSD-3-Clause | package metadata |  |
| wrapt | 2.5.1 | BSD-2-Clause | package metadata |  |
| xmltodict | 1.0.4 | MIT | package metadata |  |
| yarl | 1.25.1 | Apache-2.0 | package metadata |  |
| zipp | 4.1.2 | MIT | package metadata |  |

## Docker images

Pinned by tag in `docker-compose.yml` and the Dockerfiles. Every tag except `localstack/localstack` was pulled and run on 2026-11-17 (`make demo`), and CI pulls the ones the compose smoke test uses. Licences were read on 2026-11-17 from each project's source repository on GitHub (the licence GitHub reports for the repository, and the licence file where GitHub reports "Other"). Base-image contents (Debian packages and so on) carry their own licences, which were not checked.

| Image | Tag | Used for | Licence (source repository) |
| --- | --- | --- | --- |
| python | 3.13.5-slim | API and worker images | Python itself: Python Software Foundation License (python/cpython); image build files: MIT (docker-library/python) |
| motoserver/moto | 5.2.4 | local AWS emulator | Apache-2.0 (getmoto/moto) |
| hashicorp/terraform | 1.15.6 | `init` service | Business Source License 1.1, licensor IBM (LICENSE file at the v1.15.6 tag of hashicorp/terraform) |
| prom/prometheus | v3.5.0 | `obs` profile | Apache-2.0 (prometheus/prometheus) |
| grafana/grafana | 12.2.0 | `obs` profile | AGPL-3.0 (grafana/grafana) |
| localstack/localstack | 4.9.2 | optional `localstack` profile, off by default; needs an account token | source repository Apache-2.0 (localstack/localstack); the terms of the token-gated image were not checked |

## Terraform and provider

| Component | Version | Licence |
| --- | --- | --- |
| Terraform | 1.15.6 (`>= 1.15.0, < 2.0.0`) | Business Source License 1.1, licensor IBM (LICENSE file at the v1.15.6 tag, read 2026-11-17) |
| hashicorp/aws provider | 6.22.1 | MPL-2.0 (hashicorp/terraform-provider-aws, read 2026-11-17) |

## GitHub Actions

Pinned to full version tags in `.github/workflows/`. On 2026-11-17 each tag was looked up on GitHub: its release date, and the Node.js version in its `action.yml` (all run on Node.js 24; `upload-pages-artifact` is a composite action that calls `actions/upload-artifact` v7.0.0). Each is the oldest major version that runs on Node.js 24, at its newest patch release, and each release is more than 14 days old. Licences are the ones GitHub reports for each repository (decisions D47).

| Action | Version | Released | Licence |
| --- | --- | --- | --- |
| actions/checkout | v5.1.0 | 2026-07-20 | MIT |
| actions/setup-python | v6.3.0 | 2026-06-24 | MIT |
| hashicorp/setup-terraform | v4.0.1 | 2026-05-12 | MPL-2.0 |
| actions/configure-pages | v6.0.0 | 2026-03-25 | MIT |
| actions/upload-pages-artifact | v5.0.0 | 2026-04-10 | MIT |
| actions/deploy-pages | v5.0.1 | 2026-09-01 | MIT |

## Front-end libraries

None. `site/` is plain HTML, CSS and JavaScript. The charts are drawn as SVG by `site/app.js`, with no charting or map library and no CDN script.

## Data and map tiles

Data sources and their licences are in [data.md](data.md). No map tiles are used.

## Images

| File | Source | Licence |
| --- | --- | --- |
| `docs/media/architecture.svg` | hand-written SVG in this repo | MIT, as the rest of the repo |
| `docs/media/hero-isometric.svg` | made with Claude (Anthropic) for this repo; no third-party artwork. It carries a signed C2PA content-credentials manifest (`<metadata>`) that records this. | MIT, as the rest of the repo |
| `docs/media/demo-page-real-october-2026.png` | screenshot of this repo's demo page (headless Chrome, 2026-11-17); shows aggregates of the real October 2026 data | screenshot: MIT; the data shown: CC BY 4.0, Department of Transport and Planning (Victoria) |
| `docs/media/grafana-real-replay.png` | screenshot of Grafana 12.2.0 showing this repo's dashboard | screenshot: MIT; Grafana itself: AGPL-3.0 (see Docker images) |
| `docs/media/dagster-demo-bad-run.png` | screenshot of the Dagster UI showing the failed `make demo-bad` run (synthetic data), cropped above the stack trace | screenshot: MIT; Dagster's licence is listed with the Python packages above |
| `docs/media/dagster-asset-graph.png` | screenshot of the Dagster UI (dagster-webserver 1.13.26) showing this repo's assets | screenshot: MIT; Dagster's licence is listed with the Python packages above |
