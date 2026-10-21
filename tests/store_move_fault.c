/* Linux libc boundary observer: application operations remain real. */
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
static int selected(const char *name) {
  const char *stage=getenv("ADHD_MOVE_STAGE");
  return stage && !strcmp(stage,name);
}
static int decided(void) {
  char path[4096];
  const char *config=getenv("ADHD_MOVE_CONFIG");
  if (!config) return 0;
  snprintf(path,sizeof(path),"%s.transaction",config);
  return access(path,F_OK)==0;
}
static void stop_once(void) {
  const char *sentinel=getenv("ADHD_MOVE_SENTINEL");
  if (!sentinel || atomic_exchange(&fired,1)) return;
  int fd=open(sentinel,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
  if(fd<0) _exit(117);
  char body[512];
  int n=snprintf(body,sizeof(body),"{\"stage\":\"%s\",\"pid\":%ld}\n",getenv("ADHD_MOVE_STAGE"),(long)getpid());
  if(write(fd,body,n)!=n || fsync(fd)) _exit(118);
  close(fd);kill(getpid(),SIGSTOP);for(;;) pause();
}
int rename(const char *source,const char *destination) {
  static int (*original)(const char *,const char *);
  if(!original) original=dlsym(RTLD_NEXT,"rename");
  const char *config=getenv("ADHD_MOVE_CONFIG");char transaction[4096];
  if(config) snprintf(transaction,sizeof(transaction),"%s.transaction",config);
  int decision=config && !strcmp(destination,transaction);
  int config_write=config && !strcmp(destination,config) && decided();
  if((decision&&selected("before-decision"))||(config_write&&selected("before-config"))) stop_once();
  int result=original(source,destination);
  if(!result&&((decision&&selected("after-decision"))||(config_write&&selected("after-config")))) stop_once();
  return result;
}
int link(const char *source,const char *destination) {
  static int (*original)(const char *,const char *);
  if(!original) original=dlsym(RTLD_NEXT,"link");
  int result=original(source,destination);
  const char *target=getenv("ADHD_MOVE_TARGET");
  if(!result && target && !strncmp(destination,target,strlen(target)) && strstr(source,".move-") && decided()) {
    size_t n=strlen(destination);int snapshot=n>=9&&!strcmp(destination+n-9,".snapshot");
    if((snapshot&&selected("after-first-snapshot"))||(!snapshot&&selected("after-first-checkpoint"))) stop_once();
  }
  return result;
}
int unlink(const char *path) {
  static int (*original)(const char *);
  if(!original) original=dlsym(RTLD_NEXT,"unlink");
  const char *config=getenv("ADHD_MOVE_CONFIG");char transaction[4096];
  if(config) snprintf(transaction,sizeof(transaction),"%s.transaction",config);
  if(config&&!strcmp(path,transaction)&&selected("before-cleanup")) stop_once();
  return original(path);
}
