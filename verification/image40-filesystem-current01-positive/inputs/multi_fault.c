/* Linux-only filesystem crash fixture. No application code is replaced.
 * Every successful rename still comes from libc; the selected boundary stops
 * the actual process so the independent harness can SIGKILL it there. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static _Atomic int fired = 0;

static int has_phase(const char *path, const char *phase) {
  char body[65536], needle[128];
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  if (fd < 0) return 0;
  ssize_t count = read(fd, body, sizeof(body) - 1);
  close(fd);
  if (count <= 0) return 0;
  body[count] = 0;
  snprintf(needle, sizeof(needle), "\"phase\":\"%s\"", phase);
  return strstr(body, needle) != NULL;
}

static int transition(const char *path, char *identity, size_t capacity) {
  char body[65536];
  const char *tag = "\"eventing_transition\":{\"id\":\"";
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  if (fd < 0) return 0;
  ssize_t count = read(fd, body, sizeof(body) - 1);
  close(fd);
  if (count <= 0) return 0;
  body[count] = 0;
  char *begin = strstr(body, tag);
  if (!begin) return 0;
  begin += strlen(tag);
  char *end = strchr(begin, '"');
  if (!end || end == begin || (size_t)(end - begin) >= capacity) return 0;
  memcpy(identity, begin, (size_t)(end - begin));
  identity[end - begin] = 0;
  return 1;
}

static int contains_identity(const char *path, const char *identity) {
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  if (fd < 0) return 0;
  char *body = malloc(262144);
  if (!body) { close(fd); return 0; }
  ssize_t count = read(fd, body, 262144);
  close(fd);
  int found = count > 0 && memmem(body, (size_t)count, identity, strlen(identity)) != NULL;
  free(body);
  return found;
}

static int project_snapshot(const char *store, const char *destination) {
  size_t stem = strlen(store), size = strlen(destination);
  if (size < stem + 9 || strncmp(destination, store, stem) ||
      strcmp(destination + size - 9, ".snapshot")) return 0;
  /* Legacy base snapshot or an explicitly initialized generation below this
   * owned store root. A real decision identity must also match the source. */
  return !strcmp(destination + stem, ".snapshot") ||
    !strncmp(destination + stem, ".projects/", 10);
}

static int boundary(const char *source, const char *destination) {
  const char *stage = getenv("ADHD_CRASH_STAGE");
  const char *config = getenv("ADHD_CRASH_CONFIG");
  const char *store = getenv("ADHD_CRASH_STORE");
  char marker[4096], snapshot[4096], transaction[4096], identity[256];
  if (!stage || !config || !store || !source || !destination) return 0;
  snprintf(marker, sizeof(marker), "%s.project-upgrade", config);
  snprintf(snapshot, sizeof(snapshot), "%s.snapshot", store);
  snprintf(transaction, sizeof(transaction), "%s.transaction", config);
  if (!strcmp(stage, "transition-decision") && !strcmp(destination, config)
      && transition(transaction, identity, sizeof(identity))) return 1;
  if (!strcmp(stage, "transition-project") && project_snapshot(store, destination)
      && transition(transaction, identity, sizeof(identity)) && contains_identity(source, identity)) return 2;
  if (!strcmp(destination, marker)) {
    if (!strcmp(stage, "before-prepared") && has_phase(source, "prepared")) return 1;
    if (!strcmp(stage, "before-decided") && has_phase(source, "decided")) return 1;
    if (!strcmp(stage, "before-completed") && has_phase(source, "completed")) return 1;
  }
  if (!strcmp(stage, "before-config") && !strcmp(destination, config) && has_phase(marker, "decided")) return 1;
  if (!strcmp(stage, "after-snapshot") && !strcmp(destination, snapshot) && has_phase(marker, "decided")) return 2;
  return 0;
}

/* Schema4 migration installs a closed generation through real link/unlink,
 * instead of replacing the legacy source snapshot. Bind the observed pair to
 * the durable registry-adoption decision before stopping after link succeeds. */
static int adoption_snapshot_link(const char *source, const char *destination) {
  const char *stage = getenv("ADHD_CRASH_STAGE");
  const char *config = getenv("ADHD_CRASH_CONFIG");
  const char *store = getenv("ADHD_CRASH_STORE");
  if (!stage || strcmp(stage, "after-snapshot") || !config || !store ||
      !source || !destination || !project_snapshot(store, destination)) return 0;
  size_t a = strlen(source), b = strlen(destination);
  if (a < 9 || b < 9 || strcmp(source + a - 9, ".snapshot")) return 0;
  char path[4096], marker[4096], from[8192], to[8192];
  const size_t capacity = 1048576;
  snprintf(path, sizeof(path), "%s.transaction", config);
  snprintf(marker, sizeof(marker), "%s.project-upgrade", config);
  if (!has_phase(marker, "decided")) return 0;
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  if (fd < 0) return 0;
  char *body = malloc(capacity);
  if (!body) { close(fd); return 0; }
  ssize_t count = read(fd, body, capacity - 1);
  close(fd);
  if (count <= 0 || count == (ssize_t)capacity - 1 || a - 9 > 4000 || b - 9 > 4000) { free(body); return 0; }
  body[count] = 0;
  snprintf(from, sizeof(from), "\"stage\":\"%.*s\"", (int)a - 9, source);
  snprintf(to, sizeof(to), "\"target\":\"%.*s\"", (int)b - 9, destination);
  int matched = strstr(body, "\"kind\":\"registry_adoption\"") && strstr(body, from) && strstr(body, to);
  free(body);
  return matched;
}

static void stop_once(void) {
  const char *sentinel = getenv("ADHD_CRASH_SENTINEL");
  const char *stage = getenv("ADHD_CRASH_STAGE");
  if (!sentinel || atomic_exchange(&fired, 1)) return;
  int fd = open(sentinel, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
  if (fd < 0) _exit(117);
  char record[512];
  int length = snprintf(record, sizeof(record), "{\"stage\":\"%s\",\"pid\":%ld}\n", stage, (long)getpid());
  if (write(fd, record, length) != length || fsync(fd)) _exit(118);
  close(fd);
  /* SIGSTOP cannot be intercepted or handled by the application. */
  kill(getpid(), SIGSTOP);
  /* Process-directed stop delivery may race another BEAM thread. Never return
   * into the intercepted rename even if this thread gets a few more cycles. */
  for (;;) pause();
}

int rename(const char *source, const char *destination) {
  static int (*original)(const char *, const char *);
  if (!original) original = dlsym(RTLD_NEXT, "rename");
  int point = boundary(source, destination);
  if (point == 1) stop_once();
  int result = original(source, destination);
  if (!result && point == 2) stop_once();
  return result;
}

int renameat(int fromdir, const char *source, int todir, const char *destination) {
  static int (*original)(int, const char *, int, const char *);
  if (!original) original = dlsym(RTLD_NEXT, "renameat");
  int point = boundary(source, destination);
  if (point == 1) stop_once();
  int result = original(fromdir, source, todir, destination);
  if (!result && point == 2) stop_once();
  return result;
}

int renameat2(int fromdir, const char *source, int todir, const char *destination, unsigned int flags) {
  int point = boundary(source, destination);
  if (point == 1) stop_once();
  int result = syscall(SYS_renameat2, fromdir, source, todir, destination, flags);
  if (!result && point == 2) stop_once();
  return result;
}

int link(const char *source, const char *destination) {
  static int (*original)(const char *, const char *);
  if (!original) original = dlsym(RTLD_NEXT, "link");
  int point = adoption_snapshot_link(source, destination);
  int result = original(source, destination);
  if (!result && point) stop_once();
  return result;
}

int linkat(int fromdir, const char *source, int todir, const char *destination, int flags) {
  static int (*original)(int, const char *, int, const char *, int);
  if (!original) original = dlsym(RTLD_NEXT, "linkat");
  int point = adoption_snapshot_link(source, destination);
  int result = original(fromdir, source, todir, destination, flags);
  if (!result && point) stop_once();
  return result;
}
