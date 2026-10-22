/* Observe real Linux metadata rename+directory fsync; never substitute success. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static _Atomic int pending,fired;
static int selected(const char *destination) {
 const char *config=getenv("ADHD_REBIND_CONFIG"),*stage=getenv("ADHD_REBIND_STAGE");char target[4096];
 if(!config||!stage)return 0;
 const char *suffix=!strcmp(stage,"decision-durable")?".transaction":!strcmp(stage,"registry-durable")?".stores":!strcmp(stage,"receipt-durable")?".recovery":NULL;
 if(!suffix)return 0;
 snprintf(target,sizeof(target),"%s%s",config,suffix);return !strcmp(destination,target);
}
int rename(const char *source,const char *destination) {
 static int(*real)(const char*,const char*);if(!real)real=dlsym(RTLD_NEXT,"rename");
 int result=real(source,destination);if(result==0&&selected(destination))atomic_store(&pending,1);return result;
}
int fsync(int fd) {
 static int(*real)(int);if(!real)real=dlsym(RTLD_NEXT,"fsync");int result=real(fd);
 if(result||!atomic_load(&pending)||atomic_load(&fired))return result;
 const char *config=getenv("ADHD_REBIND_CONFIG"),*sentinel=getenv("ADHD_REBIND_SENTINEL");char link[64],path[4096],directory[4096];
 if(!config||!sentinel)return result;
 snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);ssize_t n=readlink(link,path,sizeof(path)-1);if(n<0)return result;path[n]=0;
 snprintf(directory,sizeof(directory),"%s",config);char *slash=strrchr(directory,'/');if(!slash)return result;*slash=0;
 if(strcmp(path,directory)||atomic_exchange(&fired,1))return result;
 int out=open(sentinel,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(out<0)_exit(117);
 char body[512];n=snprintf(body,sizeof(body),"{\"stage\":\"%s\",\"pid\":%ld,\"directory_fsync_result\":0}\n",getenv("ADHD_REBIND_STAGE"),(long)getpid());
 if(write(out,body,n)!=n||real(out))_exit(118);
 close(out);
 kill(getpid(),SIGSTOP);for(;;)pause();
 return result;
}
