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
           (uint64_t)((uint64_t)mono.tv_sec * NS + (uint64_t)mono.tv_nsec),
           (uint64_t)((uint64_t)boot.tv_sec * NS + (uint64_t)boot.tv_nsec),
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
  const char *canonical = !strcmp(resolved, name) ?
      "/usr/local/bin/elixir" : "/usr/local/lib/elixir/bin/elixir";
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
  int written = snprintf(out, sizeof out,
           "{\"kind\":\"image-executable-fact\",\"requested\":\"/usr/local/bin/elixir\",\"resolved\":\"%s\",\"sha256\":\"%s\",\"bytes\":%zu,\"mode\":%u,\"uid\":0,\"script_executed\":false}\n",
           canonical, hash, n, (unsigned)(before.st_mode & 07777));
  require(written >= 0 && (size_t)written < sizeof out, "probe-image-fact-output-cap");
  emit(out);
}


/* Same-container, same-UID resume for the synthetic ENV witness ONLY.  This
 * observer is explicitly not the outside-Pod memory-causal observer. */
typedef struct {
  uint64_t start, pidns, mntns, userns, dev, ino;
} ResumeIdentity;

static ResumeIdentity resume_identity(const char *nonce, const char *gate_sha,
                                      const char *argv_sha, const char *env_sha) {
  require(getpid() != 1 && getuid() == 1000 && geteuid() == 1000 &&
          getgid() == 1000 && getegid() == 1000, "resume-observer-UID");
  ResumeIdentity result = {0};
  unsigned char raw[65537];
  size_t n = proc_read(1, "stat", raw, 8192);
  raw[n] = 0;
  char *end = strrchr((char *)raw, ')');
  require(end && end[1] == ' ' && end[2] == 'T' && end[3] == ' ', "resume-gate-not-stopped");
  char *save = NULL;
  char *token = strtok_r(end + 2, " ", &save);
  unsigned field = 3;
  while (token && field < 22) { token = strtok_r(NULL, " ", &save); field++; }
  require(token != NULL && field == 22, "resume-start-field");
  result.start = number(token);
  n = proc_read(1, "status", raw, sizeof raw - 1);
  raw[n] = 0;
  char *u = strstr((char *)raw, "\nUid:\t");
  char *g = strstr((char *)raw, "\nGid:\t");
  unsigned ids[4];
  require(u && sscanf(u, "\nUid:\t%u\t%u\t%u\t%u", &ids[0], &ids[1], &ids[2], &ids[3]) == 4,
          "resume-Uid");
  for (unsigned i = 0; i < 4; i++) require(ids[i] == 1000, "resume-Uid");
  require(g && sscanf(g, "\nGid:\t%u\t%u\t%u\t%u", &ids[0], &ids[1], &ids[2], &ids[3]) == 4,
          "resume-Gid");
  for (unsigned i = 0; i < 4; i++) require(ids[i] == 1000, "resume-Gid");
  require(strstr((char *)raw, "\nPid:\t1\n") != NULL &&
          strstr((char *)raw, "\nNoNewPrivs:\t1\n") != NULL &&
          strstr((char *)raw, "\nCapEff:\t0000000000000000\n") != NULL,
          "resume-PID1-security");
  result.pidns = namespace_inode(1, "pid");
  result.mntns = namespace_inode(1, "mnt");
  result.userns = namespace_inode(1, "user");
  require(result.pidns == namespace_inode(getpid(), "pid") &&
          result.mntns == namespace_inode(getpid(), "mnt") &&
          result.userns == namespace_inode(getpid(), "user"), "resume-same-container-view");
  n = proc_read(1, "cmdline", raw, 8192);
  char hash[65];
  digest(raw, n, hash);
  require(!strcmp(hash, argv_sha), "resume-argv-hash");
  const char *args[] = {"/adhd-diagnostic/startup-gate", "gate", nonce,
                        "/usr/local/bin/elixir", "elixir", "-e", original_serve};
  size_t offset = 0;
  for (unsigned i = 0; i < 7; i++) {
    size_t size = strlen(args[i]) + 1;
    require(size <= n - offset && !memcmp(raw + offset, args[i], size), "resume-argv");
    offset += size;
  }
  require(offset == n, "resume-extra-argv");
  n = proc_read(1, "environ", raw, 65536);
  flags_ok(raw, n);
  digest(raw, n, hash);
  require(!strcmp(hash, env_sha), "resume-ordered-env-hash");
  offset = 0;
  for (unsigned i = 0; probe_environment[i]; i++) {
    size_t size = strlen(probe_environment[i]) + 1;
    require(size <= n - offset && !memcmp(raw + offset, probe_environment[i], size),
            "resume-ordered-env");
    offset += size;
  }
  require(offset == n, "resume-extra-env");
  int fd = open("/proc/1/exe", O_RDONLY | O_CLOEXEC);
  require(fd >= 0, "resume-exe-open");
  struct stat before, after;
  require(fstat(fd, &before) == 0 && S_ISREG(before.st_mode) && before.st_size > 0 &&
          before.st_size <= 1048576, "resume-exe-metadata");
  Sha sha;
  init(&sha);
  size_t total = 0;
  unsigned char chunk[4096];
  for (;;) {
    ssize_t size = read(fd, chunk, sizeof chunk);
    if (size < 0 && errno == EINTR) continue;
    require(size >= 0, "resume-exe-read");
    if (!size) break;
    total += (size_t)size;
    require(total <= 1048576, "resume-exe-cap");
    add(&sha, chunk, (size_t)size);
  }
  finish(&sha, hash);
  require(fstat(fd, &after) == 0 && before.st_dev == after.st_dev && before.st_ino == after.st_ino &&
          before.st_size == after.st_size && total == (size_t)before.st_size &&
          !strcmp(hash, gate_sha), "resume-exe-hash");
  close(fd);
  result.dev = before.st_dev;
  result.ino = before.st_ino;
  return result;
}

static void resume_gate(int argc, char **argv) {
  require(argc == 8 && hex(argv[2], 32) && hex(argv[3], 64) &&
          hex(argv[4], 64) && hex(argv[5], 64), "resume-fixed-arguments");
  uint64_t begin = now_ns();
  uint64_t expected_time = number(argv[6]);
  uint64_t release_deadline = number(argv[7]);
  require(namespace_inode(getpid(), "time") == expected_time &&
          namespace_inode(1, "time") == expected_time, "resume-host-clock-view");
  require(release_deadline > begin && release_deadline - begin <= 10 * NS,
          "resume-original-release-deadline");
  ResumeIdentity before = resume_identity(argv[2], argv[3], argv[4], argv[5]);
  int pfd = (int)syscall(SYS_pidfd_open, 1, 0);
  require(pfd >= 0, "resume-pidfd-open");
  ResumeIdentity after = resume_identity(argv[2], argv[3], argv[4], argv[5]);
  require(before.start == after.start && before.pidns == after.pidns &&
          before.mntns == after.mntns && before.userns == after.userns &&
          before.dev == after.dev && before.ino == after.ino, "resume-identity-changed");
  struct pollfd alive = {pfd, POLLIN, 0};
  require(poll(&alive, 1, 0) == 0, "resume-process-not-live");
  require(now_ns() - begin <= 2 * NS && now_ns() < release_deadline,
          "resume-observer-deadline");
  require(syscall(SYS_pidfd_send_signal, pfd, SIGCONT, NULL, 0) == 0, "resume-pidfd-CONT");
  close(pfd);
  char out[512];
  snprintf(out, sizeof out,
           "{\"kind\":\"same-container-resume\",\"pid\":1,\"uid\":1000,\"start_ticks\":%" PRIu64 ",\"pidns\":%" PRIu64 ",\"mntns\":%" PRIu64 ",\"userns\":%" PRIu64 ",\"signal\":\"pidfd-SIGCONT\",\"identity_rechecked\":true}\n",
           before.start, before.pidns, before.mntns, before.userns);
  emit(out);
}

int main(int argc, char **argv) {
  if (argc >= 2 && !strcmp(argv[1], "--resume-gate")) { resume_gate(argc, argv); return 0; }
  if (argc == 3 && !strcmp(argv[1], "-e")) { witness(argc, argv); return 0; }
  require(argc >= 2, "probe-mode");
  if (argc == 2 && !strcmp(argv[1], "--selftest")) { selftest(); return 0; }
  if (argc == 2 && !strcmp(argv[1], "--clock")) { clock_fact(); return 0; }
  if (argc == 2 && !strcmp(argv[1], "--image-fact")) { image_fact(); clock_fact(); return 0; }
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
