/* Test-only PID1 constructor: exercise exact observer exports, then block at
 * one real armed boundary. No ADHD code, fabricated I/O or structure ABI. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

_Static_assert(sizeof(off_t)==8 && sizeof(off64_t)==8,"64-bit offset ABI required");
_Static_assert(__builtin_types_compatible_p(off_t,off64_t),"identical offset ABI required");
#define BIG_OFFSET (((off_t)1 << 32) + 17)
static const char payload[]="actual scalar ABI bytes\n";
static void die(int code) { _exit(code); }
static void path(char *out,size_t cap,const char *root,const char *name) {
 int n=snprintf(out,cap,"%s/%s",root,name);if(n<0||(size_t)n>=cap)die(121);
}
static void write_all(int fd,const char *body,size_t size) {
 while(size) { ssize_t n=write(fd,body,size);if(n<=0)die(122);body+=n;size-=(size_t)n; }
}
static int fresh(const char *p) {
 int fd=open(p,O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)die(123);return fd;
}
static void bytes(const char *p) { int fd=fresh(p);write_all(fd,payload,sizeof(payload)-1);if(close(fd))die(124); }
static void check_bytes(const char *p) {
 char buf[sizeof(payload)];int fd=open(p,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)die(125);
 ssize_t n=read(fd,buf,sizeof(buf));if(n!=(ssize_t)(sizeof(payload)-1)||memcmp(buf,payload,sizeof(payload)-1)||close(fd))die(126);
}
static int is_op(const char *op,const char *wanted) { return !strcmp(op,wanted); }
static int move_call(void *fn,const char *op,const char *src,const char *dst) {
 if(is_op(op,"rename")||is_op(op,"link"))return ((int(*)(const char*,const char*))fn)(src,dst);
 if(is_op(op,"renameat")||is_op(op,"linkat")) {
  if(is_op(op,"linkat"))return ((int(*)(int,const char*,int,const char*,int))fn)(AT_FDCWD,src,AT_FDCWD,dst,0);
  return ((int(*)(int,const char*,int,const char*))fn)(AT_FDCWD,src,AT_FDCWD,dst);
 }
 if(is_op(op,"renameat2"))return ((int(*)(int,const char*,int,const char*,unsigned int))fn)(AT_FDCWD,src,AT_FDCWD,dst,0);
 die(127);return -1;
}
static void unarmed(void *fn,const char *op,const char *root) {
 char src[4096],dst[4096];path(src,sizeof(src),root,"unarmed-source");path(dst,sizeof(dst),root,"unarmed-target");
 if(is_op(op,"fsync")) {
  int fd=fresh(src);write_all(fd,payload,sizeof(payload)-1);if(((int(*)(int))fn)(fd)||close(fd))die(128);check_bytes(src);return;
 }
 if(is_op(op,"pwrite")||is_op(op,"pwrite64")) {
  int fd=fresh(src);ssize_t n;
  if(is_op(op,"pwrite64"))n=((ssize_t(*)(int,const void*,size_t,off64_t))fn)(fd,payload,sizeof(payload)-1,(off64_t)BIG_OFFSET);
  else n=((ssize_t(*)(int,const void*,size_t,off_t))fn)(fd,payload,sizeof(payload)-1,BIG_OFFSET);
  if(n!=(ssize_t)(sizeof(payload)-1)||lseek(fd,0,SEEK_END)!=BIG_OFFSET+(off_t)sizeof(payload)-1)die(129);
  char buf[sizeof(payload)];if(pread(fd,buf,sizeof(payload)-1,BIG_OFFSET)!=(ssize_t)(sizeof(payload)-1)||memcmp(buf,payload,sizeof(payload)-1)||close(fd))die(130);return;
 }
 bytes(src);
 if(is_op(op,"unlink")) { if(((int(*)(const char*))fn)(src)||access(src,F_OK)==0)die(131);return; }
 if(move_call(fn,op,src,dst))die(132);
 check_bytes(dst);
 if(is_op(op,"link")||is_op(op,"linkat"))check_bytes(src);
 else if(access(src,F_OK)==0)die(133);
}
__attribute__((constructor)) static void probe(void) {
 const char *op=getenv("ADHD_ABI_OP");if(!op||getpid()!=1)return;
 const char *root=getenv("ADHD_ABI_ROOT"),*lib=getenv("ADHD_ABI_OBSERVER"),*prefix=getenv("ADHD_ABI_PREFIX"),*stage=getenv("ADHD_ABI_STAGE");
 if(!root||!lib||!prefix||!stage||strlen(stage)>100||strlen(prefix)>100)die(134);
 char key[128];int k=snprintf(key,sizeof(key),"%sSTAGE",prefix);if(k<0||(size_t)k>=sizeof(key))die(135);
 if(unsetenv(key))die(136);
 void *handle=dlopen(lib,RTLD_NOW|RTLD_NOLOAD);if(!handle)die(137);
 void *fn=dlsym(handle,op);if(!fn)die(138);
 /* This lookup originates AFTER the observer in the preload list, so it must
  * resolve the real musl forwarding target, not recursively our wrapper. */
 const char *forward=is_op(op,"renameat2")?"syscall:renameat2":op;
 void *next=is_op(op,"renameat2")?NULL:dlsym(RTLD_NEXT,op);
 if(is_op(op,"pwrite64")&&!next) { next=dlsym(RTLD_NEXT,"pwrite");forward="pwrite"; }
 if(!is_op(op,"renameat2")&&(!next||next==fn))die(139);
 unarmed(fn,op,root);
 char trace[4096],body[512];path(trace,sizeof(trace),root,"caller.json");
 int fd=fresh(trace);int n=snprintf(body,sizeof(body),"{\"op\":\"%s\",\"namespace_pid\":1,\"wrapper_resolved\":true,\"next_resolved_distinct\":%s,\"direct_syscall\":%s,\"unarmed_success\":true,\"real_forwarding_symbol\":\"%s\",\"off_t_bytes\":%zu,\"off64_t_bytes\":%zu,\"sparse_offset\":%lld}\n",op,is_op(op,"renameat2")?"false":"true",is_op(op,"renameat2")?"true":"false",forward,sizeof(off_t),sizeof(off64_t),(long long)((is_op(op,"pwrite")||is_op(op,"pwrite64"))?BIG_OFFSET:0));
 if(n<0||(size_t)n>=sizeof(body))die(140);
 write_all(fd,body,(size_t)n);if(fsync(fd)||close(fd))die(141);
 if(setenv(key,stage,1))die(142);
 const char *src=getenv("ADHD_ABI_SOURCE"),*dst=getenv("ADHD_ABI_TARGET");if(!src||!dst)die(143);
 if(is_op(op,"fsync")) {
  const char *prepare=getenv("ADHD_ABI_PREPARE_RENAME");
  if(prepare&&*prepare) { void *rename_fn=dlsym(handle,"rename");if(!rename_fn||((int(*)(const char*,const char*))rename_fn)(prepare,dst))die(144); }
  const char *sync=getenv("ADHD_ABI_SYNC");if(!sync)die(145);
  int syncfd=open(sync,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(syncfd<0)die(146);
  ((int(*)(int))fn)(syncfd);
 } else if(is_op(op,"unlink")) ((int(*)(const char*))fn)(dst);
 else if(is_op(op,"pwrite")||is_op(op,"pwrite64")) {
  int target=open(dst,O_RDWR|O_CLOEXEC|O_NOFOLLOW);if(target<0)die(147);
  if(is_op(op,"pwrite64"))((ssize_t(*)(int,const void*,size_t,off64_t))fn)(target,payload,sizeof(payload)-1,(off64_t)BIG_OFFSET);
  else ((ssize_t(*)(int,const void*,size_t,off_t))fn)(target,payload,sizeof(payload)-1,BIG_OFFSET);
 } else {
  if(move_call(fn,op,src,dst))die(149);
  const char *after=getenv("ADHD_ABI_AFTER_RENAME_SYNC");
  if(after&&*after) {
   void *syncfn=dlsym(handle,"fsync");if(!syncfn)die(150);
   int dirfd=open(after,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(dirfd<0)die(151);
   ((int(*)(int))syncfn)(dirfd);
  }
 }
 /* A real armed observer must never return to the caller. */
 die(148);
}
