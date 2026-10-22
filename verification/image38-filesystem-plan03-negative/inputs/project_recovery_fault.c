/* Observe real Linux libc operations. Never replace data or fake I/O success. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static _Atomic int fired, route_writes, decision_renamed;
static int same(const char *a, const char *b) { return a && b && !strcmp(a,b); }
static int selected(const char *name) { return same(getenv("ADHD_RECOVERY_FAULT_STAGE"),name); }
static int armed(void) {
  const char *path=getenv("ADHD_RECOVERY_FAULT_ARM");
  return path && access(path,F_OK)==0;
}
static int owned(const char *path,const char *suffix) {
  const char *config=getenv("ADHD_RECOVERY_FAULT_CONFIG");
  char expected[PATH_MAX];
  if(!config || snprintf(expected,sizeof(expected),"%s%s",config,suffix)>=(int)sizeof(expected)) return 0;
  return same(path,expected);
}
static int decided(void) {
  const char *config=getenv("ADHD_RECOVERY_FAULT_CONFIG");
  char path[PATH_MAX];
  if(!config || snprintf(path,sizeof(path),"%s.transaction",config)>=(int)sizeof(path)) return 0;
  return access(path,F_OK)==0;
}
static int stage_snapshot(const char *path) {
  const char *root=getenv("ADHD_RECOVERY_FAULT_ROOT");
  size_t n=path?strlen(path):0;
  return root && path && !strncmp(root,path,strlen(root)) && path[strlen(root)]=='/' &&
    strstr(path,".restore-") && n>=20 && !strcmp(path+n-20,"/state.dets.snapshot");
}
static int private_path(const char *path) {
  const char *root=getenv("ADHD_RECOVERY_FAULT_ROOT");
  return root && path && !strncmp(root,path,strlen(root)) && path[strlen(root)]=='/';
}
static void stop_once(void) {
  const char *sentinel=getenv("ADHD_RECOVERY_FAULT_SENTINEL");
  if(!sentinel || atomic_exchange(&fired,1)) return;
  int fd=open(sentinel,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
  if(fd<0) _exit(117);
  char body[512];
  int n=snprintf(body,sizeof(body),"{\"stage\":\"%s\",\"pid\":%ld}\n",getenv("ADHD_RECOVERY_FAULT_STAGE"),(long)getpid());
  if(n<0 || n>=(int)sizeof(body) || write(fd,body,(size_t)n)!=n || fsync(fd)) _exit(118);
  close(fd);
  kill(getpid(),SIGSTOP);
  for(;;) pause();
}
int rename(const char *source,const char *target) {
  static int (*next)(const char *,const char *);
  if(!next) next=dlsym(RTLD_NEXT,"rename");
  int active=armed(), decision=active&&owned(target,".transaction"), stage=active&&stage_snapshot(target);
  if((stage&&selected("before-stage-snapshot")) || (decision&&selected("before-decision"))) stop_once();
  int result=next(source,target);
  if(!result && active) {
    if(stage&&selected("after-stage-snapshot")) stop_once();
    if(decision) {
      atomic_store(&decision_renamed,1);
      if(selected("after-decision")) stop_once();
    }
    if(decided() && owned(target,".stores")) {
      int count=atomic_fetch_add(&route_writes,1)+1;
      if((count==1&&selected("after-route-selected")) || (count==2&&selected("after-route-ready"))) stop_once();
    }
    if(decided() && owned(target,".recovery") && atomic_load(&route_writes)>=2 && selected("after-completion")) stop_once();
  }
  return result;
}
int fsync(int fd) {
  static int (*next)(int);
  if(!next) next=dlsym(RTLD_NEXT,"fsync");
  int result=next(fd);
  if(!result && armed() && !atomic_load(&fired) && atomic_load(&decision_renamed) && selected("after-decision-sync")) {
    char proc[64],path[PATH_MAX],parent[PATH_MAX];
    const char *config=getenv("ADHD_RECOVERY_FAULT_CONFIG");
    snprintf(proc,sizeof(proc),"/proc/self/fd/%d",fd);
    ssize_t n=readlink(proc,path,sizeof(path)-1);
    if(config && n>0) {
      path[n]=0;
      if(strlen(config)<sizeof(parent)) {
        strcpy(parent,config);char *slash=strrchr(parent,'/');
        if(slash) { *slash=0; if(same(path,parent)) stop_once(); }
      }
    }
  }
  return result;
}
int link(const char *source,const char *target) {
  static int (*next)(const char *,const char *);
  if(!next) next=dlsym(RTLD_NEXT,"link");
  int result=next(source,target);
  if(!result && armed() && decided() && private_path(source) && private_path(target) && strstr(source,".restore-")) {
    size_t n=strlen(target);int snapshot=n>=9&&!strcmp(target+n-9,".snapshot");
    if((snapshot&&selected("after-install-snapshot")) || (!snapshot&&selected("after-install-checkpoint"))) stop_once();
  }
  return result;
}
int unlink(const char *path) {
  static int (*next)(const char *);
  if(!next) next=dlsym(RTLD_NEXT,"unlink");
  int decision=armed()&&owned(path,".transaction");
  if(decision&&selected("before-cleanup")) stop_once();
  int result=next(path);
  if(!result&&decision&&selected("after-cleanup")) stop_once();
  return result;
}
