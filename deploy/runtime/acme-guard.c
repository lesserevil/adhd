/* SPDX-License-Identifier: Apache-2.0
 * Linux process-lifetime guardian. No shell, hooks, daemon mode or network I/O.
 * timeout is the REMAINING accepted order budget, captured once on entry.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static void signal_stop(int number) { stopped = number; }
static int64_t now_ms(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) _exit(125);
    return (int64_t)value.tv_sec * 1000 + value.tv_nsec / 1000000;
}
static int number(const char *value, int maximum) {
    char *end = NULL;
    if (!value || !*value || *value == '-' || *value == '+') return -1;
    errno = 0;
    long parsed = strtol(value, &end, 10);
    if (errno || *end || parsed < 1 || parsed > maximum) return -1;
    return (int)parsed;
}
static void group_signal(pid_t child, int number) {
    /* child is always the fork-created, owned process-group identifier. */
    if (kill(-child, number) < 0 && errno != ESRCH) _exit(125);
}
/* Fixed private root lock. Walk without symlinks; never truncate/rewrite it. */
static int private_lock(const char *path) {
    if (path[0] != '/' || strlen(path) >= PATH_MAX) return -1;
    char copy[PATH_MAX];
    memcpy(copy, path + 1, strlen(path));
    int directory = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (directory < 0) return -1;
    char *part = copy;
    for (;;) {
        char *slash = strchr(part, '/');
        if (slash) *slash = '\0';
        if (!*part || !strcmp(part, ".") || !strcmp(part, "..")) {
            close(directory); return -1;
        }
        if (!slash) break;
        int next = openat(directory, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        close(directory);
        if (next < 0) return -1;
        directory = next;
        part = slash + 1;
    }
    struct stat info;
    if (fstat(directory, &info) || info.st_uid != geteuid() || (info.st_mode & 0077)) {
        close(directory); return -1;
    }
    int lock = openat(directory, part, O_RDWR | O_CREAT | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
    close(directory);
    if (lock < 0) return -1;
    if (fstat(lock, &info) || !S_ISREG(info.st_mode) || info.st_nlink != 1 ||
        info.st_uid != geteuid() || (info.st_mode & 07777) != 0600) {
        close(lock); return -1;
    }
    if (flock(lock, LOCK_EX | LOCK_NB)) {
        int busy = errno == EWOULDBLOCK || errno == EAGAIN;
        close(lock); return busy ? -2 : -1;
    }
    return lock; /* held until process exit, after group cleanup and waitpid */
}
int main(int argc, char **argv) {
    const int64_t entered = now_ms();
    if (argc == 3 && !strcmp(argv[1], "--probe-lock")) {
        int lock = private_lock(argv[2]);
        return lock >= 0 ? 0 : lock == -2 ? 75 : 125;
    }
    if (argc < 9 || strcmp(argv[1], "--lock-file") ||
        strcmp(argv[3], "--timeout-ms") || strcmp(argv[5], "--grace-ms") ||
        strcmp(argv[7], "--") || argv[8][0] != '/') return 64;
    int timeout = number(argv[4], 3600000), grace = number(argv[6], 5000);
    if (timeout < 0 || grace < 0) return 64;
    const int64_t deadline = entered + timeout;
    pid_t owner = getppid();
    if (owner < 1) return 125;
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = signal_stop;
    sigemptyset(&action.sa_mask);
    for (int i = 0; i < 3; ++i) {
        const int signals[] = {SIGTERM, SIGINT, SIGHUP};
        if (sigaction(signals[i], &action, NULL)) return 125;
    }
    /* Subreaping lets us wait for ordinary descendants after killing our group. */
    if (prctl(PR_SET_CHILD_SUBREAPER, 1) ||
        prctl(PR_SET_PDEATHSIG, SIGTERM) || getppid() != owner) return 125;
    int lock = private_lock(argv[2]);
    if (lock == -2) return 75;
    if (lock < 0) return 125;
    if (getppid() != owner || stopped) return 125;
    if (now_ms() >= deadline) return 124;
    pid_t guardian_self = getpid();
    pid_t child = fork();
    if (child < 0) return 125;
    if (child == 0) {
        if (setpgid(0, 0) || prctl(PR_SET_PDEATHSIG, SIGKILL) ||
            getppid() != guardian_self) _exit(125);
        struct sigaction reset;
        memset(&reset, 0, sizeof(reset));
        reset.sa_handler = SIG_DFL;
        sigemptyset(&reset.sa_mask);
        if (sigaction(SIGTERM, &reset, NULL) || sigaction(SIGINT, &reset, NULL) ||
            sigaction(SIGHUP, &reset, NULL)) _exit(125);
        int nullfd = open("/dev/null", O_RDONLY | O_CLOEXEC);
        if (nullfd < 0 || dup2(nullfd, STDIN_FILENO) < 0) _exit(125);
        if (nullfd != STDIN_FILENO) close(nullfd);
        execv(argv[8], argv + 8);
        _exit(127);
    }
    if (setpgid(child, child) < 0 && errno != EACCES && errno != ESRCH) {
        kill(child, SIGKILL);
        while (waitpid(child, NULL, 0) < 0 && errno == EINTR) {}
        return 125;
    }
    int status = 0, finished = 0, reason = 0;
    for (;;) {
        /* Keep the direct child unreaped until group signalling is complete:
         * its reserved PID prevents accidental process-group ID reuse. */
        siginfo_t exited;
        memset(&exited, 0, sizeof(exited));
        if (waitid(P_PID, (id_t)child, &exited, WEXITED | WNOHANG | WNOWAIT) < 0) {
            if (errno == EINTR) continue;
            reason = 125; break;
        }
        if (exited.si_pid == child) break;
        if (stopped) { reason = 125; break; }
        int64_t remaining = deadline - now_ms();
        if (remaining <= 0) { reason = 124; break; }
        struct pollfd input = {STDIN_FILENO, POLLIN | POLLHUP | POLLERR, 0};
        int ready = poll(&input, 1, remaining < 25 ? (int)remaining : 25);
        if (ready < 0 && errno != EINTR) { reason = 125; break; }
        if (ready > 0) {
            if (input.revents & (POLLERR | POLLNVAL)) { reason = 125; break; }
            if (input.revents & (POLLIN | POLLHUP)) {
                char data[256];
                ssize_t read_count = read(STDIN_FILENO, data, sizeof(data));
                if (read_count == 0 || (read_count < 0 && errno != EINTR)) {
                    reason = 125; break;
                }
            }
        }
    }
    /* Even a successful direct child must not leave a process in its group. */
    group_signal(child, SIGTERM);
    int64_t stop_at = now_ms() + grace;
    while (now_ms() < stop_at) {
        struct timespec pause = {0, 5000000};
        nanosleep(&pause, NULL);
    }
    group_signal(child, SIGKILL);
    /* All managed children have been killed; wait/reap before reporting closed. */
    for (;;) {
        int value;
        pid_t result = waitpid(-1, &value, 0);
        if (result > 0) {
            if (result == child) { status = value; finished = 1; }
        } else if (result < 0 && errno == EINTR) continue;
        else if (result < 0 && errno == ECHILD) break;
        else return 125;
    }
    if (reason) return reason;
    if (!finished) return 125;
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return WIFSIGNALED(status) ? 128 + WTERMSIG(status) : 125;
}
