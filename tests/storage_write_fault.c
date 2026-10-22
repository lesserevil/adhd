/* Test-only real successful libc write boundary observer, armed after baseline. */
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
static int selected(const char *stage,char *target,size_t cap) {
  const char *s=getenv("ADHD_WRITE_STAGE"),*arm=getenv("ADHD_WRITE_ARM"),*control=getenv("ADHD_WRITE_TARGET");
  if(atomic_load(&fired)||!s||strcmp(s,stage)||!arm||access(arm,F_OK)||!control) return 0;
  int fd=open(control,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0) return 0;
  ssize_t n=read(fd,target,cap-1);close(fd);if(n<=0||(size_t)n>=cap-1) return 0;
  target[n]=0;return 1;
}
static int contains_mutation(const char *path) {
  const size_t cap=1024*1024;char *body=malloc(cap);if(!body) return 0;
  int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0){free(body);return 0;}
  ssize_t n=read(fd,body,cap);close(fd);
  int yes=n>0&&(size_t)n<cap&&memmem(body,(size_t)n,"crash-request",13)!=NULL;free(body);return yes;
}
static void stop_once(const char *call) {
  const char *sentinel=getenv("ADHD_WRITE_SENTINEL");if(!sentinel||atomic_exchange(&fired,1)) return;
  int fd=open(sentinel,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0) _exit(117);
  char body[512];int n=snprintf(body,sizeof(body),"{\"stage\":\"%s\",\"pid\":%ld,\"syscall\":\"%s\"}\n",getenv("ADHD_WRITE_STAGE"),(long)getpid(),call);
  if(write(fd,body,(size_t)n)!=n||fsync(fd)) _exit(118);
  close(fd);kill(getpid(),SIGSTOP);for(;;) pause();
}
static int fd_path(int fd,char *path,size_t cap) {
  char proc[64];snprintf(proc,sizeof(proc),"/proc/self/fd/%d",fd);ssize_t n=readlink(proc,path,cap-1);
  if(n<0||(size_t)n>=cap-1)return 0;
  path[n]=0;return 1;
}
static void checkpoint_written(int fd,const char *call) {
  char target[4096],path[4096],snapshot[4140];
  if(selected("checkpoint-write",target,sizeof(target))&&fd_path(fd,path,sizeof(path))&&!strcmp(path,target)) {
    snprintf(snapshot,sizeof(snapshot),"%s.snapshot",target);if(contains_mutation(snapshot))stop_once(call);
  }
}
int fsync(int fd) {
  static int (*real)(int);if(!real)real=dlsym(RTLD_NEXT,"fsync");int result=real(fd);
  if(result)return result;
  char target[4096],path[4096],snapshot[4140];
  if(selected("snapshot-data-sync",target,sizeof(target))&&fd_path(fd,path,sizeof(path))) {
    snprintf(snapshot,sizeof(snapshot),"%s.snapshot.tmp-",target);
    if(!strncmp(path,snapshot,strlen(snapshot))&&contains_mutation(path))stop_once("fsync");
  }
  if(selected("checkpoint-sync",target,sizeof(target))&&fd_path(fd,path,sizeof(path))&&!strcmp(path,target)) {
    snprintf(snapshot,sizeof(snapshot),"%s.snapshot",target);if(contains_mutation(snapshot))stop_once("fsync");
  }
  return result;
}
int rename(const char *source,const char *destination) {
  static int (*real)(const char *,const char *);if(!real)real=dlsym(RTLD_NEXT,"rename");int result=real(source,destination);
  char target[4096],snapshot[4140];
  if(!result&&selected("snapshot-install",target,sizeof(target))) {
    snprintf(snapshot,sizeof(snapshot),"%s.snapshot",target);if(!strcmp(destination,snapshot)&&contains_mutation(destination))stop_once("rename");
  }
  return result;
}
ssize_t pwrite(int fd,const void *buf,size_t count,off_t offset) {
  static ssize_t (*real)(int,const void *,size_t,off_t);if(!real)real=dlsym(RTLD_NEXT,"pwrite");ssize_t n=real(fd,buf,count,offset);if(n>=0)checkpoint_written(fd,"pwrite");return n;
}
ssize_t pwrite64(int fd,const void *buf,size_t count,off64_t offset) {
  static ssize_t (*real)(int,const void *,size_t,off64_t);if(!real)real=dlsym(RTLD_NEXT,"pwrite64");ssize_t n=real(fd,buf,count,offset);if(n>=0)checkpoint_written(fd,"pwrite64");return n;
}
