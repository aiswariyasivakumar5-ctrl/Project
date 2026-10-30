# Independent data evaluation plan

September 21, 2026: candidate sources inspected; external evaluation has not run.

| Candidate | Observed source material | Compatibility/permission gap |
|---|---|---|
| [MCPTox-Benchmark](https://github.com/zhiqiangwang4/MCPTox-Benchmark) | Tool definitions, `pure_tool.json`, `response_all.json`, analysis notebook | No license file was visible in the inspected root listing. Permission and exact dataset scope need verification. Metadata poisoning examples are not automatically complete labeled runtime sessions. |
| [MCPSecBench](https://github.com/AIS2Lab/MCPSecBench) | Benchmark code/data and MIT license shown in repository | Inspect the pinned revision, data-specific terms and actual event schema before use. Requires an adapter and a server/session split; running third-party attack scripts is unnecessary for initial offline inspection. |

Before importing data, pin a source revision and file hashes, record applicable
permission, and inspect its structure without executing supplied scripts. Establish
which fields are real observations and which would require reconstruction. Synthetic
responses/timings added by an adapter must be labeled as reconstructed, not represented
as measured independent runtime traces.

Hold out entire servers or sessions before fitting preprocessing. Deduplicate related
attack templates across splits. Preserve attack family and benign controls. Record
redactions without retaining credentials, and never send private project material to
external benchmark services. Evaluate frozen thresholds and report incompatibilities.

No external-data accuracy, independent-trace validation or dataset permission is
asserted by this planning document. The first next step is data-schema and license
inspection at a pinned revision, followed by an explicit adapter/split protocol.

## September 25 pinned-schema inspection

Read-only inspection of MCPSecBench revision
`7612c5a3e811dcf01f64e4f2bb324591a2feaaf4` found three files under `data/`:
`README.md`, `data.json`, and `experiments.csv`. No third-party code was executed
and no benchmark prompts were sent to a model or live server.

The [JSON dataset](https://github.com/AIS2Lab/MCPSecBench/blob/7612c5a3e811dcf01f64e4f2bb324591a2feaaf4/data/data.json)
contains 11 attack-prompt specifications with fields `attack`, `prompt`, and
`result`. The last field contains grading instructions, not an observed tool
response. The [data documentation](https://github.com/AIS2Lab/MCPSecBench/blob/7612c5a3e811dcf01f64e4f2bb324591a2feaaf4/data/README.md)
describes outcome codes and screenshots. These materials do not provide the
ordered request/response events, measured latency, session/server identifiers,
or benign enrollment traffic needed for Sentinel's independent runtime evaluation.

The pinned root [license](https://github.com/AIS2Lab/MCPSecBench/blob/7612c5a3e811dcf01f64e4f2bb324591a2feaaf4/LICENSE)
is MIT, copyright 2025 AIS2Lab. No separate data terms were observed in the
inspected data directory. Attribution/license notices must accompany reuse;
this inspection is not a legal review of third-party materials.

SHA-256 of fetched text re-encoded as UTF-8 (line endings preserved):

| File | SHA-256 |
|---|---|
| LICENSE | `3af8ed82d7f5c04ff28ae586c4b030858db1ab617cdf2ad8da00e6dc566f2c06` |
| data/data.json | `037b3824147d3c0b674af66fd27095e51a2379a4bf91b65861315de594e6ae48` |
| data/README.md | `a6de3be6acf6a4f047e6ef98a77b2d256d05d025dec29cd6de463adb57de4594` |

Decision: do not fabricate an adapter that turns prompts into measured runtime
traces. Independent evaluation remains blocked on suitable licensed event-level
data or an approved, isolated trace-collection study. A template-derived synthetic
test could be separate future evidence, but cannot satisfy this requirement.
