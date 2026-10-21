# Durable broker installation identity

The shipped single-broker deployment MUST use a unique Kafka cluster ID for each
new installation and preserve it across replacements and restores. The optional
explicit `CLUSTER_ID` is an identity assertion; it MUST NOT replace the identity
of an existing volume. Operators of a separately reviewed multi-node topology
must provision the same explicit ID to every node of that one cluster.

Before executing the pinned Confluent startup, the read-only Python bootstrap
MUST validate every configured log directory's existing KRaft `meta.properties`
and reconcile their cluster/node IDs with any `.adhd-cluster-id` seed and explicit
assertion. Mismatches, symlinks, malformed/ambiguous metadata or unidentified
nonempty log directories fail before formatting. Existing metadata, including
volumes created by the former shared tutorial-ID deployment, remains authoritative
and is adopted without changing Kafka metadata or deleting records.

When there is no existing identity, generate one using the selected broker's
`kafka-storage random-uuid`. Commit an owner-only seed on the same durable volume
using exclusive installation and file/directory synchronization before launching
Kafka. An interrupted first boot resumes the committed seed. Never generate a
replacement identity for a partial/damaged nonempty data directory. Backup and
restore the seed with the entire broker volume. The small bootstrap lock fences
concurrent seed provisioning; the supported deployment still requires one broker
owner and Kafka's own log-directory locking, not a new distributed lock claim.

Compose mounts `kafka-bootstrap.py` read-only. The Kubernetes ConfigMap contains
the same exact bytes; the independent bootstrap probe MUST reject drift. The
wrapper uses only Python's standard library already present in the pinned Kafka
image and then executes the original Confluent entrypoint unchanged. It does not
format storage or implement a Kafka client.

Confluent requires a unique ID per KRaft cluster in its [Docker configuration
reference](https://docs.confluent.io/platform/8.3/installation/docker/config-reference.html).
The pinned 8.3.2 image's `/etc/confluent/docker/configure` requires `CLUSTER_ID`;
its `ensure` invokes storage formatting and treats already-formatted storage as
success. It provides no installation-specific seed or assertion reconciliation,
which is why this deployment supplies the narrow bootstrap.
