# Third-party notices

The files in `src/iac_eval_bench/data/schemas/` are unmodified standalone strict
Kubernetes 1.34.0 JSON schemas from
[yannh/kubernetes-json-schema](https://github.com/yannh/kubernetes-json-schema),
revision `93153a1458e24e93f386c50f9980d584fcba574b`.

The upstream Apache-2.0 license notice is retained in `UPSTREAM-LICENSE` beside
the schema files. The full license is available in `APACHE-2.0.txt` in that directory.
`manifest.json` records each source URL and SHA-256 checksum. Schema loading
verifies these hashes before evaluation. These files are derived from Kubernetes
OpenAPI definitions; the generator project and Kubernetes are independent of this project.

Original project code, task prompts, grading rules and fixtures use the root MIT
license. Runtime dependencies retain their own licenses. No upstream task dataset
is included.
