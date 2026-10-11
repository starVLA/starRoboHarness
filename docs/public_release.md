# Public release boundary

The public repository contains reusable contracts, adapters, manifests, examples, tests, documentation, and sanitized figures. It must not contain provider tokens, SSH details, cluster paths, account names, raw reasoning transcripts, raw RPC payloads, checkpoints, datasets, simulator installations, or unreviewed rollout bundles.

Before a public push:

1. run the repository secret scan and inspect every match;
2. check that examples use environment variables or placeholders;
3. remove local absolute paths from manifests and logs;
4. include only aggregate metrics whose protocol and denominator are documented;
5. attach a checksum manifest for any release asset;
6. run the public namespace and contract tests.

Private evidence remains in the internal repository and ModelScope backup. The public repository can point to the paper, project page, and released aggregate results without exposing operational data.
