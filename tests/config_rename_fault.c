/* Test-only real successful rename observer, armed after fixture bootstrap. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static _Atomic int fired;

int rename(const char *source, const char *destination) {
  static int (*original)(const char *, const char *);
  if (!original) original = dlsym(RTLD_NEXT, "rename");
  if (!original) _exit(116);
  int result = original(source, destination);
  const char *stage = getenv("ADHD_CONFIG_FAULT_STAGE");
  const char *config = getenv("ADHD_CONFIG_FAULT_CONFIG");
  const char *arm = getenv("ADHD_CONFIG_FAULT_ARM");
  const char *sentinel = getenv("ADHD_CONFIG_FAULT_SENTINEL");
  if (result || !stage || !config || !arm || !sentinel || access(arm, F_OK)) return result;
  const char *suffix;
  if (!strcmp(stage, "transaction")) suffix = ".transaction";
  else if (!strcmp(stage, "config")) suffix = "";
  else if (!strcmp(stage, "journal")) suffix = ".journal";
  else return result;
  char target[4096];
  int n = snprintf(target, sizeof(target), "%s%s", config, suffix);
  if (n < 0 || (size_t)n >= sizeof(target) || strcmp(destination, target)) return result;
  if (atomic_exchange(&fired, 1)) return result;
  int fd = open(sentinel, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
  if (fd < 0) _exit(117);
  char body[256];
  n = snprintf(body, sizeof(body), "{\"stage\":\"%s\",\"pid\":%ld,\"rename_result\":0}\n", stage, (long)getpid());
  if (n < 0 || (size_t)n >= sizeof(body) || write(fd, body, n) != n || fsync(fd)) _exit(118);
  close(fd);
  kill(getpid(), SIGSTOP);
  for (;;) pause();
}
