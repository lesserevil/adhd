#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

/* Scoped to the owned legacy-producer process; no service/firewall changes. */
int connect(int fd, const struct sockaddr *address, socklen_t length) {
  static int (*next_connect)(int, const struct sockaddr *, socklen_t);
  if (!next_connect) next_connect = dlsym(RTLD_NEXT, "connect");
  const char *text = getenv("ADHD_RECOVERY_DENY_PROVIDER_PORT");
  int port = text ? atoi(text) : 0;
  int actual = 0;
  if (address && address->sa_family == AF_INET && length >= sizeof(struct sockaddr_in))
    actual = ntohs(((const struct sockaddr_in *)address)->sin_port);
  if (address && address->sa_family == AF_INET6 && length >= sizeof(struct sockaddr_in6))
    actual = ntohs(((const struct sockaddr_in6 *)address)->sin6_port);
  if (port > 0 && actual == port) {
    const char *path = getenv("ADHD_RECOVERY_PROVIDER_FENCE_AUDIT");
    if (path) {
      int out = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
      if (out >= 0) {
        const char line[] = "blocked-provider-connect\n";
        ssize_t count = write(out, line, sizeof(line) - 1);
        (void)count;
        (void)close(out);
      }
    }
    errno = ECONNREFUSED;
    return -1;
  }
  return next_connect(fd, address, length);
}
