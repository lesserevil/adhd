/* Standalone TEST PROBE only. Includes the exact reviewed source unchanged.
 * This file is not an application, gate deployment, or cluster executor.
 * Compilation and every native/container execution require separate root GO.
 */
#define main counter19_original_entry
#include "policy_kind_counter.c"
#undef main

static char *const probe_environment[] = {
  "HOME=/tmp", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C",
  "ERL_FLAGS=+S 2:2", "ERL_FLAGS=+S 1:1", NULL
};

static void sha_equal(const void *data, size_t n, const char *expected) {
  char hash[65];
  digest(data, n, hash);
  require(!strcmp(hash, expected), "probe-SHA-mismatch");
}

static void selftest(void) {
  sha_equal("", 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  sha_equal("abc", 3, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  sha_equal("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", 56,
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
  Sha s;
  init(&s);
  unsigned char a[1000];
  memset(a, 'a', sizeof a);
  for (unsigned i = 0; i < 1000; i++) add(&s, a, sizeof a);
  char hash[65];
  finish(&s, hash);
  require(!strcmp(hash, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
          "probe-million-a-SHA");
  const char *uid = "88e9a64a-e762-401c-8ac7-a7f008d67c72";
  const char *cid = "8888888888888888888888888888888888888888888888888888888888888888";
  const char *meta = "kubelet-kubepods-burstable-pod88e9a64a_e762_401c_8ac7_a7f008d67c72.slice:cri-containerd:8888888888888888888888888888888888888888888888888888888888888888";
  char parent[512], child[640], absolute[768];
  expected_paths(meta, uid, cid, parent, child);
  require(!strcmp(parent, "/kubelet.slice/kubelet-kubepods.slice/kubelet-kubepods-burstable.slice/kubelet-kubepods-burstable-pod88e9a64a_e762_401c_8ac7_a7f008d67c72.slice"), "probe-parent");
  require(snprintf(absolute, sizeof absolute, "/sys/fs/cgroup%s", parent) < (int)sizeof absolute,
          "probe-mount-join-size");
  require(!strncmp(absolute, "/sys/fs/cgroup/kubelet.slice/", 28), "probe-mount-join");
  require(!strcmp(child + strlen(parent), "/cri-containerd-8888888888888888888888888888888888888888888888888888888888888888.scope"), "probe-child");
  require(number("0") == 0 && number("18446744073709551615") == UINT64_MAX,
          "probe-number-positive");
  emit("{\"kind\":\"native-selftest\",\"sha_vectors\":4,\"exact_path_vectors\":1,\"number_vectors\":2,\"passed\":true}\n");
}

static void environment_bytes(unsigned char out[65536], size_t *size) {
  *size = 0;
  for (char **entry = environ; *entry; entry++) {
    size_t n = strlen(*entry) + 1;
    require(n <= 65536 - *size, "probe-environment-cap");
    memcpy(out + *size, *entry, n);
    *size += n;
  }
}

static void witness(int argc, char **argv) {
  require(getuid() == 1000 && geteuid() == 1000 && getgid() == 1000 && getegid() == 1000,
          "probe-witness-UID");
  require(argc == 3 && !strcmp(argv[0], "elixir") && !strcmp(argv[1], "-e") &&
          !strcmp(argv[2], original_serve), "probe-original-argv");
  size_t index = 0;
  while (probe_environment[index]) {
    require(environ[index] && !strcmp(environ[index], probe_environment[index]),
            "probe-environment-order");
    index++;
  }
  require(environ[index] == NULL, "probe-extra-environment");
  unsigned char bytes[65536];
  size_t n;
  environment_bytes(bytes, &n);
  flags_ok(bytes, n);
  char env_hash[65], serve_hash[65];
  digest(bytes, n, env_hash);
  digest(original_serve, strlen(original_serve), serve_hash);
  char out[512];
  snprintf(out, sizeof out,
           "{\"kind\":\"raw-environment-exec-witness\",\"ordered_env_sha256\":\"%s\",\"SERVE_sha256\":\"%s\",\"entries\":5,\"ERL_FLAGS\":[\"+S 2:2\",\"+S 1:1\"],\"original_argv_verified\":true,\"passed\":true}\n",
           env_hash, serve_hash);
  emit(out);
}

static void launch(const char *nonce) {
  require(hex(nonce, 32), "probe-nonce");
  require(getuid() == 1000 && geteuid() == 1000 && getgid() == 1000 && getegid() == 1000,
          "probe-launcher-UID");
  char *argv[] = {"/adhd-diagnostic/startup-gate", "gate", (char *)nonce,
                  "/usr/local/bin/elixir", "elixir", "-e", (char *)original_serve, NULL};
  /* Deliberate duplicate environment is constructed only by this native launcher.
   * Docker/sh environment normalization is not used as preservation evidence. */
  execve(argv[0], argv, probe_environment);
  fail("probe-launch-execve");
}

static void clock_fact(void) {
  struct timespec mono, boot;
  require(clock_gettime(CLOCK_MONOTONIC, &mono) == 0 &&
          clock_gettime(CLOCK_BOOTTIME, &boot) == 0, "probe-clock");
  char out[512];
  snprintf(out, sizeof out,
           "{\"kind\":\"clock-fact\",\"monotonic_ns\":%" PRIu64 ",\"boottime_ns\":%" PRIu64 ",\"time_namespace_inode\":%" PRIu64 ",\"time_for_children_namespace_inode\":%" PRIu64 "}\n",
           (uint64_t)mono.tv_sec * NS + (uint64_t)mono.tv_nsec,
           (uint64_t)boot.tv_sec * NS + (uint64_t)boot.tv_nsec,
           namespace_inode(getpid(), "time"), namespace_inode(getpid(), "time_for_children"));
  emit(out);
}

static void image_fact(void) {
  /* Fixed source-image executable resolution only. No script or BEAM execution. */
  const char *name = "/usr/local/bin/elixir";
  char resolved[PATH_MAX];
  require(realpath(name, resolved) != NULL, "probe-image-executable-resolution");
  require(!strcmp(resolved, name) || !strcmp(resolved, "/usr/local/lib/elixir/bin/elixir"),
          "probe-image-executable-unexpected-target");
  int fd = open(resolved, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  require(fd >= 0, "probe-image-executable-open");
  struct stat before, after;
  require(fstat(fd, &before) == 0 && S_ISREG(before.st_mode) && before.st_uid == 0 &&
          !(before.st_mode & 0022) && (before.st_mode & 0111) &&
          before.st_size > 0 && before.st_size <= 65536, "probe-image-executable-metadata");
  unsigned char bytes[65536];
  size_t n = read_fd(fd, bytes, sizeof bytes);
  require(fstat(fd, &after) == 0 && before.st_dev == after.st_dev &&
          before.st_ino == after.st_ino && before.st_size == after.st_size &&
          n == (size_t)before.st_size, "probe-image-executable-changed");
  close(fd);
  require(n >= 10 && !memcmp(bytes, "#!/bin/sh\n", 10), "probe-image-executable-shebang");
  char hash[65], out[512];
  digest(bytes, n, hash);
  snprintf(out, sizeof out,
           "{\"kind\":\"image-executable-fact\",\"requested\":\"/usr/local/bin/elixir\",\"resolved\":\"%s\",\"sha256\":\"%s\",\"bytes\":%zu,\"mode\":%u,\"uid\":0,\"script_executed\":false}\n",
           resolved, hash, n, (unsigned)(before.st_mode & 07777));
  emit(out);
}

int main(int argc, char **argv) {
  if (argc == 3 && !strcmp(argv[1], "-e")) { witness(argc, argv); return 0; }
  require(argc >= 2, "probe-mode");
  if (argc == 2 && !strcmp(argv[1], "--selftest")) { selftest(); return 0; }
  if (argc == 2 && !strcmp(argv[1], "--clock")) { clock_fact(); return 0; }
  if (argc == 2 && !strcmp(argv[1], "--image-fact")) { image_fact(); return 0; }
  if (argc == 3 && !strcmp(argv[1], "--env-launcher")) { launch(argv[2]); return 70; }
  require(argc == 2, "probe-reject-mode-arity");
  if (!strcmp(argv[1], "--reject-leading-zero")) (void)number("01");
  else if (!strcmp(argv[1], "--reject-overflow")) (void)number("18446744073709551616");
  else if (!strcmp(argv[1], "--reject-number-tail")) (void)number("1x");
  else if (!strcmp(argv[1], "--reject-environment")) {
    const unsigned char bad[] = "ERL_FLAGS=+S 9:9\0";
    flags_ok(bad, sizeof bad - 1);
  } else if (!strcmp(argv[1], "--reject-path")) {
    char parent[512], child[640];
    expected_paths("/foreign/../kubelet.slice", "88e9a64a-e762-401c-8ac7-a7f008d67c72",
                   "8888888888888888888888888888888888888888888888888888888888888888", parent, child);
  } else fail("probe-mode");
  fail("probe-rejection-did-not-reject");
}
