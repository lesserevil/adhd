/* Observe the real completed checkpoint-backup rename, then continue on SIGCONT. */
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
int rename(const char *source,const char *destination) {
  static int (*real)(const char *,const char *);
  if(!real)real=dlsym(RTLD_NEXT,"rename");
  int result=real(source,destination);
  const char *target=getenv("ADHD_ADOPTION_TARGET"),*sentinel=getenv("ADHD_ADOPTION_SENTINEL");
  if(!result&&target&&sentinel&&!strcmp(target,destination)&&!atomic_exchange(&fired,1)) {
    int fd=open(sentinel,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)_exit(117);
    char body[256];int n=snprintf(body,sizeof(body),"{\"stage\":\"after-checkpoint-backup-rename\",\"pid\":%ld}\n",(long)getpid());
    if(write(fd,body,(size_t)n)!=n||fsync(fd))_exit(118);
    close(fd);kill(getpid(),SIGSTOP);
  }
  return result;
}
