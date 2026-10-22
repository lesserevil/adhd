---
name: Derived contextual indexes
summary: Rebuildable immutable row inputs, native text ranking and atomic generations
kind: component
---
# Derived contextual indexes

Index originals, not extracted domain facts or model-generated summaries. A row binds
publication ID, original record identity, context identity, ingestion sequence,
context-input manifest and fragment hashes. Index each record with its own original
text, JSON data, source/type metadata and optional communication context. Context
traversal is bounded at the generation's frozen source watermark, including incoming
replies/corrections and matching communication groups up to that watermark. Private
or unresolved references never contribute content. External URLs are never fetched.

Rows and generations are immutable versions. New publications invalidate affected
connected context rows and produce new input identities in the next generation;
originals never change. Incremental planning includes newly indexed rows and all
existing indexed roots connected within the recipe traversal depth (including direct
resolved links and communication groups). Reuse unaffected immutable rows. A build
may conservatively recompute additional rows, but must not miss affected ones.

A frozen query never reads future context from a newer index. If the active generation
was built at a different source watermark, reconstruct eligible contextual rows from
originals at the query's watermark before computing its frozen ranking. Record this
materialization and the exact scope input-manifest identity. An older generation
cannot silently certify coverage of a newer snapshot; wait/catch up or report stale.
Later publications cannot change an old query's ranking, scores or comparisons.

## Fragment and manifest rules

Fragments preserve UTF8 text exactly and split only at Unicode codepoint byte
boundaries. Fields are text, data, context.question, context.subject,
context.conversation, context.task, context.external.snapshot, information_type, author_id, created_at, occurred_at,
source.kind, source.id, source.item_id or source.uri. Data fragments use JSON serialization of
original data, explicitly labeled as such, not original input JSON lexical bytes.
Every fragment has origin_publication_id, origin_identity, origin_context_identity,
field, start/end (inclusive/exclusive UTF8 byte offsets into that field's full
serialized value), text and sha256 over exact UTF8 text. Omit empty text and missing optional metadata; data serialization includes JSON
null and empty objects/arrays/strings as original values. Do not invent content. A fragment indexed for a root record can originate
from a bounded older public context record; retain both root and origin provenance.

Rows contain at most256 fragments. If bounds prevent fully indexing own content,
mark the row/index partial and expose the missing count; never claim full coverage.
Context traversal gaps/truncation stay separate from primary original coverage.
Index up to max_records oldest publications in ingestion order, report excluded
original count if archive exceeds the bound. Do not silently sample a complete index.
Source manifest is ingestion-ordered {publication_id,identity,context_identity,
input_identity,fragment_sha256s}; input_identity hashes the ordered public
record/context identity list and exact fragment hashes. These canonical manifests
contain only strings, integers, booleans and arrays/objects. No float JSON canonical
hash is invented. Actual serialized fragments remain hash-verifiable across encoders.
Adapter/recipe changes invalidate incompatible derived rows and trigger rebuild.

Keep active, previous and at mostone staging generation. Generation IDs are opaque,
server-local and distinct. Native content has adapter_version="adhd-native-retrieval-v1",
no embedding model. The generation manifest binds server ID, runtime, recipe/identity, indexed-through watermark, source
watermark/manifest, total/indexed/excluded originals, fragment count, context gaps,
bytes, creation/update times, state and error. Public manifest excludes term postings,
credentials, original private data and endpoint URLs. States building,ready,partial,
failed; top-level status may additionally be missing,stale,disabled. A ready generation
is current only at the present last-publication watermark, desired recipe and
current max_records coverage plan. A hot capacity change exposes stale/building
until the replacement manifest reflects that limit.

Asynchronous builds take bounded batches from frozen original inputs outside Store,
then commit only to the same staging generation, recipe, cursor and source identities.
Persist build cursor and rows before acknowledging progress. A process kill retries
from the last committed cursor without duplicate rows. Concurrent publications extend
catch-up; recheck last-publication watermark inside the final atomic switch. Never
activate a generation claiming current coverage while a publication is missing.
Retain previous usable generation for rollback. Failed or resource-limited staging
keeps active data; raising hot limits/rebuilding can recover. Index updates and
retirement must never delete originals or alter queues, source retries or credentials.

Incremental catch-up preserves unaffected immutable rows, replaces affected context
rows with new versions, and indexes new publications. An
old active watermark is stale until catch-up commits. Old query results/requests stay
frozen. Index storage is bounded separately by max_index_bytes with65536 bytes reserved
for errors/progress. Report RESOURCE_LIMIT without blocking ingestion. Reconstruct
corrupt/incompatible DERIVED row state from originals with explicit unavailable status;
do not disguise corruption in authoritative originals as an index error.

## Exact initial ranking

Tokenize field fragments, never generated interpretations. words uses maximal Unicode
letter/number/underscore sequences, case-folded with the runtime's Unicode lowercase;
identifiers additionally retains maximal ASCII [A-Za-z0-9_.:/-]+ identifiers and their
word tokens. Adapter/runtime identity changes must be visible when normalization or
serialization changes. No stemmer, domain synonym table, or predicted ingestion class.

For a frozen, AND-filtered primary scope, compute document frequencies, document count
and mean token length using only those eligible indexed rows. Future publications and
out-of-scope records cannot change the BM25 statistics used in a frozen replay.
For each distinct question token t use BM25 k1=1.2,b=0.75:
IDF=ln(1+(N-df(t)+0.5)/(df(t)+0.5)); contribution=IDF*tf(t)*2.2 /
(tf(t)+1.2*(0.25+0.75*length/mean_length)). Sum contributions; empty corpus/question
terms yield0. Normalize lexical score round(1000000*score/(1+score)). Sort initial
rows descending lexical score, then descending ingestion sequence, then ascending
publication ID. This deterministic order supplies at most semantic_window records
for semantic scoring. The run record budget bounds examined work and checkpoints
partial progress rather than silently reducing that declared target. Expose all limits and unexamined
scope; no bounded window is exhaustive.

Semantic usefulness scores are integer ppm, not truth/support. Final score is integer
floor((lexical_weight*lexical_ppm + semantic_weight*semantic_ppm)/(sum weights));
unexamined semantic values contribute0 ONLY for ranking and remain explicitly null
in public evidence, never a recorded negative judgment. Semantic disabled uses
lexical score directly. Eligible candidates have lexical score>0 or a valid semantic
score>=min_confidence_ppm. Sort descending final score, descending lexical score,
descending ingestion sequence and ascending publication ID; return at most requested
limit, with explicit truncation. Every ranked candidate retains original/context and
fragment provenance plus lexical/semantic scores and assessed/unassessed status.

Model assembly selects at most model_fragments whole indexed fragments per candidate,
prioritizing its recorded question, then its original text/data, then remaining
fragments by question-token overlap and stable field/start/origin order. Bound the
exact request bytes; omit whole fragments with explicit truncation, never cut one
silently. If no complete useful fragment fits, report CONTEXT_LIMIT. This is candidate
scoring over declared fragments, not full-record assessment. Fetch complete originals
and frozen context before any later support judgment. Negated statements can be highly
relevant; their similarity is not positive evidence that the statement happened.

## Qualified optimization overrides

Optimization/selection.md owns effective recipe overrides, atomic caught-up
promotion/rollback and durable operator reset. Resolve the operator config and
authoritative Store selection explicitly for every read, build, lease and commit;
keep matching/federation generation config raw. Ordinary catchup preserves an
applied selection’s protected rollback generation. Include private optimizer
generations in the shared native capacity; a ranking-only variant may reuse
structurally identical rows without claiming a new native build. Corrupt derived
state cannot clear or invent authoritative selection.
