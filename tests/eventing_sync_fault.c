/* Independent Linux fsync boundary probe; no application code/data is changed. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
static _Atomic int fired=0;
static int match(int fd,char *path,size_t size) {
 const char *store=getenv("ADHD_EVENT_STORE"),*arm=getenv("ADHD_EVENT_ARM"),*stage=getenv("ADHD_EVENT_STAGE");
 if(!store||!arm||!stage||access(arm,F_OK))return 0;
 char link[64];snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);
 ssize_t n=readlink(link,path,size-1);if(n<=0)return 0;path[n]=0;
 char prefix[4096];snprintf(prefix,sizeof(prefix),"%s.snapshot.tmp-",store);
 return !strcmp(stage,"fanout-before-sync")? !strncmp(path,prefix,strlen(prefix)):!strcmp(path,store);
}
static void stop(int fd,const char *path,const char *call,int result) {
 if(atomic_exchange(&fired,1))return;
 const char *sentinel=getenv("ADHD_EVENT_SENTINEL"),*stage=getenv("ADHD_EVENT_STAGE");
 int out=open(sentinel,O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);if(out<0)_exit(117);
 char body[8192];int n=snprintf(body,sizeof(body),"{\"stage\":\"%s\",\"pid\":%ld,\"fd\":%d,\"path\":\"%s\",\"syscall\":\"%s\",\"result\":%d}\n",stage,(long)getpid(),fd,path,call,result);
 if(write(out,body,n)!=n)_exit(118);close(out);
 kill(getpid(),SIGSTOP);for(;;)pause();
}
int fsync(int fd) {
 static int(*real)(int);if(!real)real=dlsym(RTLD_NEXT,"fsync");
 char path[4096];int selected=match(fd,path,sizeof(path));const char *stage=getenv("ADHD_EVENT_STAGE");
 if(selected&&!strcmp(stage,"fanout-before-sync"))stop(fd,path,"fsync",-1);
 int result=real(fd);if(selected&&result==0)stop(fd,path,"fsync",result);return result;
}
int fdatasync(int fd) {
 static int(*real)(int);if(!real)real=dlsym(RTLD_NEXT,"fdatasync");
 char path[4096];int selected=match(fd,path,sizeof(path));const char *stage=getenv("ADHD_EVENT_STAGE");
 if(selected&&!strcmp(stage,"fanout-before-sync"))stop(fd,path,"fdatasync",-1);
 int result=real(fd);if(selected&&result==0)stop(fd,path,"fdatasync",result);return result;
}
