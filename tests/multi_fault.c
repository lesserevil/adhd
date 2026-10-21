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

static int boundary(const char *source, const char *destination) {
  const char *stage = getenv("ADHD_CRASH_STAGE");
  const char *config = getenv("ADHD_CRASH_CONFIG");
  const char *store = getenv("ADHD_CRASH_STORE");
  char marker[4096], snapshot[4096];
  if (!stage || !config || !store || !source || !destination) return 0;
  snprintf(marker, sizeof(marker), "%s.project-upgrade", config);
  snprintf(snapshot, sizeof(snapshot), "%s.snapshot", store);
  if (!strcmp(destination, marker)) {
    if (!strcmp(stage, "before-prepared") && has_phase(source, "prepared")) return 1;
    if (!strcmp(stage, "before-decided") && has_phase(source, "decided")) return 1;
    if (!strcmp(stage, "before-completed") && has_phase(source, "completed")) return 1;
  }
  if (!strcmp(stage, "before-config") && !strcmp(destination, config) && has_phase(marker, "decided")) return 1;
  if (!strcmp(stage, "after-snapshot") && !strcmp(destination, snapshot) && has_phase(marker, "decided")) return 2;
  return 0;
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
