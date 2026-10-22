/* NetworkPolicy TCP fixture only. No hub/Kafka/BEAM behavior is qualified.
 * Build separately with reviewed static compiler closure; never compile in gate. */
#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

/* Elixir source literal "adhd-policy-v1\n", decoded once. */
static const unsigned char banner[] = {97,100,104,100,45,112,111,108,105,99,121,45,118,49,10};
static int64_t now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) exit(3);
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static int wait_fd(int fd, short events, int64_t deadline) {
    struct pollfd p = {fd, events, 0};
    for (;;) {
        int64_t left = deadline - now_ms();
        if (left <= 0) { errno = ETIMEDOUT; return 0; }
        int n = poll(&p, 1, (int)left);
        if (n < 0 && errno == EINTR) continue;
        if (!n) errno = ETIMEDOUT;
        return n;
    }
}
static int denied(int e) {
    return e == ETIMEDOUT || e == EHOSTUNREACH || e == ENETUNREACH || e == ECONNREFUSED;
}
static int probe(const char *host, const char *raw_port) {
    char *end; long port = strtol(raw_port, &end, 10);
    struct sockaddr_in a = {0}; a.sin_family = AF_INET;
    if (*end || port < 1 || port > 65535 || inet_pton(AF_INET, host, &a.sin_addr) != 1) return 3;
    a.sin_port = htons((uint16_t)port);
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return 3;
    if (fcntl(fd, F_SETFL, O_NONBLOCK) < 0) { close(fd); return 3; }
    int64_t deadline = now_ms() + 1000;
    int rc = connect(fd, (struct sockaddr *)&a, sizeof(a)), error = errno;
    if (rc && error == EINPROGRESS) {
        rc = wait_fd(fd, POLLOUT, deadline);
        if (rc > 0) { socklen_t n = sizeof(error); if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &n)) error = errno; }
        else error = rc == 0 ? ETIMEDOUT : errno;
    } else if (!rc) error = 0;
    if (error) { close(fd); if (denied(error)) { puts("DENIED"); return 0; } return 3; }
    unsigned char got[sizeof(banner)]; size_t used = 0;
    deadline = now_ms() + 1000;
    while (used < sizeof(got)) {
        if (wait_fd(fd, POLLIN, deadline) <= 0) { close(fd); return 2; }
        ssize_t n = recv(fd, got + used, sizeof(got) - used, 0);
        if (n < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (n <= 0) { close(fd); return 2; }
        used += (size_t)n;
    }
    close(fd);
    if (memcmp(got, banner, sizeof(banner))) return 2;
    puts("REACHABLE"); return 0;
}
static int serve(void) {
    const int ports[] = {8082, 9092, 9093}; struct pollfd listeners[3];
    signal(SIGPIPE, SIG_IGN);
    for (int i = 0; i < 3; i++) {
        int fd = socket(AF_INET, SOCK_STREAM, 0), yes = 1;
        struct sockaddr_in a = {0}; a.sin_family = AF_INET; a.sin_port = htons(ports[i]); a.sin_addr.s_addr = htonl(INADDR_ANY);
        if (fd < 0 || setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes)) ||
            bind(fd, (struct sockaddr *)&a, sizeof(a)) || listen(fd, 128)) return 3;
        listeners[i] = (struct pollfd){fd, POLLIN, 0};
    }
    for (;;) {
        int rc = poll(listeners, 3, -1);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0) return 3;
        for (int i = 0; i < 3; i++) if (listeners[i].revents) {
            if (!(listeners[i].revents & POLLIN)) return 3;
            int fd = accept(listeners[i].fd, NULL, NULL);
            if (fd < 0 && errno == EINTR) continue;
            if (fd < 0) return 3;
            size_t sent = 0;
            while (sent < sizeof(banner)) {
                ssize_t n = send(fd, banner + sent, sizeof(banner) - sent, 0);
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) break;
                sent += (size_t)n;
            }
            close(fd);
        }
    }
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "serve")) return serve();
    if (argc == 4 && !strcmp(argv[1], "probe")) return probe(argv[2], argv[3]);
    return 3;
}
