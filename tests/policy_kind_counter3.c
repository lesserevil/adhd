/* Test-only stopped-startup/cgroup observer. Never linked into ADHD.
* Uncompiled preparation: execution requires separately reviewed ELF/tool bindings.
* Linux x86_64, unified cgroup2, exact one already-owned PID/Pod/CID only.
*/
#define _GNU_SOURCE
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <linux/nsfs.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
extern char **environ;
#define CGROUP2_MAGIC 0x63677270
#define MAX_OUTPUT (8U*1024U*1024U)
#define MAX_SAMPLES 256U
#define NS 1000000000ULL
static const char original_serve[] = "\nfor port <- [8082, 9092, 9093] do\n  spawn_link(fn ->\n    {:ok, socket} = :gen_tcp.listen(port, [:binary, active: false, reuseaddr: true])\n    Stream.repeatedly(fn ->\n      {:ok, client} = :gen_tcp.accept(socket)\n      :gen_tcp.send(client, \"adhd-policy-v1\\n\")\n      :gen_tcp.close(client)\n    end) |> Stream.run()\n  end)\nend\nProcess.sleep(:infinity)\n";
static size_t output_bytes;
static void fail(const char *code) {
  dprintf(2,"counter19 rejected: %s\n",code);
  _exit(70);
}
static void require(int ok,const char *code) {
  if(!ok)fail(code);
}
static uint64_t now_ns(void) {
  struct timespec t;
  require(clock_gettime(CLOCK_MONOTONIC,&t)==0,"clock");
  return (uint64_t)t.tv_sec*NS+(uint64_t)t.tv_nsec;
}
static uint64_t boot_ns(void) {
  struct timespec t;
  require(clock_gettime(CLOCK_BOOTTIME,&t)==0,"boot-clock");
  return (uint64_t)((uint64_t)t.tv_sec*NS+(uint64_t)t.tv_nsec);
}
static void emit(const char *s) {
  size_t n=strlen(s);
  require(n<=MAX_OUTPUT-output_bytes,"output-cap");
  output_bytes+=n;
  while(n){
    ssize_t k=write(1,s,n);
    if(k<0&&errno==EINTR)continue;
    require(k>0,"output-write");
    s+=k;
    n-=(size_t)k;
  }
}
static int hex(const char *s,size_t n) {
  if(strlen(s)!=n)return 0;
  for(size_t i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
  return 1;
}
static int uid_ok(const char *s) {
  if(strlen(s)!=36)return 0;
  for(size_t i=0;i<36;i++){
    if(i==8||i==13||i==18||i==23){
      if(s[i]!='-')return 0;
    }
    else if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
  }
  return 1;
}
static uint64_t number(const char *s) {
  require(*s&&(*s!='0'||!s[1]),"decimal");
  uint64_t x=0;
  for(;*s;s++){
    require(*s>='0'&&*s<='9'&&x<=(UINT64_MAX-(unsigned)(*s-'0'))/10,"decimal");
    x=x*10+(unsigned)(*s-'0');
  }
  return x;
}
/* Independent small SHA-256 implementation; no dynamic crypto/library lookup. */
typedef struct {
  uint32_t h[8];
  uint64_t bytes;
  unsigned char b[64];
  size_t used;
} Sha;
static uint32_t rr(uint32_t x,unsigned n){
  return (x>>n)|(x<<(32-n));
}
static void block(Sha *s,const unsigned char *b){
  static const uint32_t k[64]={
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  };
  uint32_t w[64];
  for(unsigned i=0;i<16;i++)w[i]=((uint32_t)b[4*i]<<24)|((uint32_t)b[4*i+1]<<16)|((uint32_t)b[4*i+2]<<8)|b[4*i+3];
  for(unsigned i=16;i<64;i++){
    uint32_t a=w[i-15],c=w[i-2];
    w[i]=w[i-16]+(rr(a,7)^rr(a,18)^(a>>3))+w[i-7]+(rr(c,17)^rr(c,19)^(c>>10));
  }
  uint32_t a=s->h[0],c=s->h[2],b0=s->h[1],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
  for(unsigned i=0;i<64;i++){
    uint32_t t=h+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^(~e&g))+k[i]+w[i];
    uint32_t u=(rr(a,2)^rr(a,13)^rr(a,22))+((a&b0)^(a&c)^(b0&c));
    h=g;
    g=f;
    f=e;
    e=d+t;
    d=c;
    c=b0;
    b0=a;
    a=t+u;
  }
  s->h[0]+=a;
  s->h[1]+=b0;
  s->h[2]+=c;
  s->h[3]+=d;
  s->h[4]+=e;
  s->h[5]+=f;
  s->h[6]+=g;
  s->h[7]+=h;
}
static void init(Sha *s){
  *s=(Sha){
    .h={
      0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19
    }
  };
}
static void add(Sha *s,const void *data,size_t n){
  const unsigned char *b=data;
  s->bytes+=n;
  while(n){
    size_t k=64-s->used;
    if(k>n)k=n;
    memcpy(s->b+s->used,b,k);
    s->used+=k;
    b+=k;
    n-=k;
    if(s->used==64){
      block(s,s->b);
      s->used=0;
    }
  }
}
static void finish(Sha *s,char out[65]){
  uint64_t bits=s->bytes*8;
  unsigned char one=128,zero=0;
  add(s,&one,1);
  while(s->used!=56)add(s,&zero,1);
  unsigned char tail[8];
  for(unsigned i=0;i<8;i++)tail[7-i]=(unsigned char)(bits>>(8*i));
  add(s,tail,8);
  for(unsigned i=0;i<8;i++)snprintf(out+8*i,9,"%08x",s->h[i]);
}
static void digest(const void *b,size_t n,char out[65]){
  Sha s;
  init(&s);
  add(&s,b,n);
  finish(&s,out);
}
static size_t read_fd(int fd,unsigned char *buf,size_t cap){
  size_t n=0;
  for(;;){
    ssize_t k=read(fd,buf+n,cap-n);
    if(k<0&&errno==EINTR)continue;
    require(k>=0,"read");
    if(!k)return n;
    n+=(size_t)k;
    if(n==cap){
      unsigned char more;
      do{
        k=read(fd,&more,1);
      }
      while(k<0&&errno==EINTR);
      require(k==0,"read-cap");
      return n;
    }
  }
}
static size_t proc_read(pid_t pid,const char *leaf,unsigned char *buf,size_t cap){
  char p[128];
  require(snprintf(p,sizeof p,"/proc/%ld/%s",(long)pid,leaf)<(int)sizeof p,"proc-path");
  int fd=open(p,O_RDONLY|O_CLOEXEC);
  require(fd>=0,"proc-open");
  size_t n=read_fd(fd,buf,cap);
  require(close(fd)==0,"proc-close");
  return n;
}
static uint64_t namespace_inode(pid_t pid,const char *leaf){
  char p[128];
  require(snprintf(p,sizeof p,"/proc/%ld/ns/%s",(long)pid,leaf)<(int)sizeof p,"ns-path");
  struct stat s;
  require(stat(p,&s)==0,"namespace");
  return (uint64_t)s.st_ino;
}
/* /proc/PID/timens_offsets reports time_ns_for_children.  Only use it as
 * current-clock proof when this process's current/children namespaces match.
 * Different processes may have DIFFERENT inodes with identical zero offsets. */
static void parse_zero_time_offsets(const unsigned char *raw, size_t n) {
  require(n > 0 && n < 512 && raw[n - 1] == '\n' && !memchr(raw, 0, n),
          "time-offsets-shape");
  char copy[512];
  memcpy(copy, raw, n);
  copy[n] = 0;
  const char *expected[] = {"monotonic", "0", "0", "boottime", "0", "0"};
  char *save = NULL;
  char *token = strtok_r(copy, " \t\n", &save);
  for (unsigned i = 0; i < 6; i++) {
    require(token != NULL && !strcmp(token, expected[i]), "time-offsets-not-exact-zero");
    token = strtok_r(NULL, " \t\n", &save);
  }
  require(token == NULL, "time-offsets-extra");
}

static uint64_t zero_time_namespace(pid_t pid) {
  uint64_t current = namespace_inode(pid, "time");
  uint64_t children = namespace_inode(pid, "time_for_children");
  require(current == children, "time-offsets-current-children-view");
  unsigned char raw[512];
  size_t n = proc_read(pid, "timens_offsets", raw, sizeof raw);
  parse_zero_time_offsets(raw, n);
  require(current == namespace_inode(pid, "time") &&
          children == namespace_inode(pid, "time_for_children"), "time-namespace-changed");
  return current;
}

static void expected_paths(const char *raw,const char *uid,const char *cid,char parent[512],char child[640]){
  require(uid_ok(uid)&&hex(cid,64),"pod-cid");
  char u[37];
  strcpy(u,uid);
  for(unsigned i=0;i<36;i++)if(u[i]=='-')u[i]='_';
  char pod[128],meta[256];
  int found=0;
  const char *qos[]={
    "","burstable","besteffort"
  };
  for(unsigned i=0;i<3;i++){
    snprintf(parent,512,"/kubepods/%spod%s",i==0?"":(i==1?"burstable/":"besteffort/"),uid);
    snprintf(child,640,"%s/%s",parent,cid);
    if(!strcmp(raw,child)){
      found=1;
      break;
    }
    char prefix[64];
    snprintf(prefix,sizeof prefix,"kubepods%s%s",i?"-":"",qos[i]);
    snprintf(pod,sizeof pod,"%s-pod%s.slice",prefix,u);
    if(i)snprintf(parent,512,"/kubepods.slice/%s.slice/%s",prefix,pod);
    else snprintf(parent,512,"/kubepods.slice/%s",pod);
    snprintf(child,640,"%s/cri-containerd-%s.scope",parent,cid);
    snprintf(meta,sizeof meta,"%s:cri-containerd:%s",pod,cid);
    if(!strcmp(raw,child)||!strcmp(raw,meta)){
      found=1;
      break;
    }
  }
  if(!found){
    snprintf(pod,sizeof pod,"kubelet-kubepods-burstable-pod%s.slice",u);
    snprintf(parent,512,"/kubelet.slice/kubelet-kubepods.slice/kubelet-kubepods-burstable.slice/%s",pod);
    snprintf(child,640,"%s/cri-containerd-%s.scope",parent,cid);
    snprintf(meta,sizeof meta,"%s:cri-containerd:%s",pod,cid);
    found=!strcmp(raw,child)||!strcmp(raw,meta);
  }
  require(found,"unsupported-cgroup-layout");
}
typedef struct {
  pid_t pid;
  const char *uid,*cid,*nonce,*gate_sha,*argv_sha,*env_sha,*cri_path;
  uint64_t deadline;
} Input;
typedef struct {
  uint64_t start,pidns,mntns,cgns,timens,observer_timens,dev,ino,blocked_signals;
  char state;
  char actual_cgroup[640],parent[512],child[640];
} Identity;
static void flags_ok(const unsigned char *b,size_t n){
  require(n&&b[n-1]==0,"environ-NUL");
  unsigned count=0;
  for(size_t i=0;i<n;){
    size_t k=strnlen((const char *)b+i,n-i);
    require(k<n-i,"environ-NUL");
    if(k>=10&&!memcmp(b+i,"ERL_FLAGS=",10)){
      const char *v=(const char *)b+i+10;
      require(!strcmp(v,"+S 2:2")||!strcmp(v,"+S 1:1"),"ERL_FLAGS");
      count++;
    }
    i+=k+1;
  }
  require(count>=1&&count<=2,"ERL_FLAGS-count");
}
static void mount_view(void){
  unsigned char raw[65536];
  int fd=open("/proc/self/mountinfo",O_RDONLY|O_CLOEXEC);
  require(fd>=0,"mountinfo");
  size_t n=read_fd(fd,raw,sizeof raw-1);
  close(fd);
  raw[n]=0;
  unsigned matches=0;
  char *save=NULL;
  for(char *line=strtok_r((char *)raw,"\n",&save);line;line=strtok_r(NULL,"\n",&save)){
    if(!strstr(line," - cgroup2 "))continue;
    char a[32],b[32],dev[32],root[256],point[256];
    require(sscanf(line,"%31s %31s %31s %255s %255s",a,b,dev,root,point)==5,"mountinfo-fields");
    require(!strcmp(root,"/")&&!strcmp(point,"/sys/fs/cgroup"),"unsupported-cgroup-mount-view");
    matches++;
  }
  require(matches==1,"ambiguous-cgroup2-mount");
}
/* Parse only the kernel's fixed-width signal-mask fields for this PID. */
static uint64_t status_signal_mask(const char *status, const char *key) {
  const char *p = strstr(status, key);
  require(p != NULL, "signal-status-field");
  p += strlen(key);
  require(strlen(p)>=17,"signal-status-short-field");
  uint64_t value = 0;
  for (unsigned i = 0; i < 16; i++) {
    unsigned char c = (unsigned char)p[i];
    unsigned digit;
    if (c >= '0' && c <= '9') digit = c - '0';
    else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
    else fail("signal-status-hex");
    value = (value << 4) | digit;
  }
  require(p[16] == '\n', "signal-status-width");
  return value;
}

/* Exact target namespace ancestry only; no PID or namespace discovery scan.
 * A different inode alone is not used as proof of ancestor authority. */
static void require_pid_ancestor(pid_t target, uint64_t expected_target,
                                 uint64_t expected_observer) {
  char path[128];
  require(snprintf(path, sizeof path, "/proc/%ld/ns/pid", (long)target) < (int)sizeof path,
          "ancestor-path");
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  require(fd >= 0, "ancestor-namespace-open");
  struct stat st, observer;
  require(stat("/proc/self/ns/pid", &observer) == 0 &&
          (uint64_t)observer.st_ino == expected_observer, "ancestor-observer-identity");
  require(fstat(fd, &st) == 0 && st.st_dev == observer.st_dev &&
          (uint64_t)st.st_ino == expected_target,
          "ancestor-target-identity");
  unsigned found = 0;
  for (unsigned depth = 0; depth < 32; depth++) {
    int parent = ioctl(fd, NS_GET_PARENT);
    require(parent >= 0, "ancestor-parent-unavailable");
    require(fcntl(parent, F_SETFD, FD_CLOEXEC) == 0, "ancestor-parent-cloexec");
    close(fd);
    fd = parent;
    require(fstat(fd, &st) == 0, "ancestor-parent-stat");
    if (st.st_dev == observer.st_dev && (uint64_t)st.st_ino == expected_observer) { found = 1; break; }
  }
  close(fd);
  require(found, "observer-not-proven-PID-ancestor");
}

static char process_state(pid_t pid) {
  unsigned char raw[8193];
  size_t n = proc_read(pid, "stat", raw, sizeof raw - 1);
  raw[n] = 0;
  char expected[32];
  int size = snprintf(expected, sizeof expected, "%ld (", (long)pid);
  require(size > 0 && size < (int)sizeof expected && n >= (size_t)size &&
          !memcmp(raw, expected, (size_t)size), "proc-PID-view");
  char *end = strrchr((char *)raw, ')');
  require(end != NULL && end[1] == ' ' && end[3] == ' ', "proc-state");
  return end[2];
}

static void wait_for_kernel_stop(const Input *x, int pidfd) {
  uint64_t limit = now_ns() + NS;
  if (limit > x->deadline - 20 * NS) limit = x->deadline - 20 * NS;
  while (now_ns() < limit) {
    struct pollfd alive = {pidfd, POLLIN, 0};
    require(poll(&alive, 1, 0) == 0, "stop-target-not-live");
    char state = process_state(x->pid);
    if (state == 'T') return;
    require(state == 'S' || state == 'R', "stop-target-unexpected-state");
    struct timespec delay = {0, 1000000};
    while (nanosleep(&delay, &delay) < 0) require(errno == EINTR, "stop-wait");
  }
  fail("actual-kernel-T-not-observed");
}

/* No global PID/cgroup discovery: only the authenticated CRI PID is read. */
static Identity identity(const Input *x, char phase){
  Identity v={
    0
  };
  unsigned char b[65537];
  size_t n=proc_read(x->pid,"stat",b,8192);
  b[n]=0;
  char *end=strrchr((char *)b,')');
  require(end&&end[1]==' '&&end[3]==' ',"gate-state-format");
  v.state=end[2];
  require(phase=='W' ? (v.state=='S'||v.state=='R') : (phase=='T'&&v.state=='T'),
          phase=='W' ? "gate-not-cooperatively-waiting" : "gate-not-kernel-stopped");
  char *save=NULL,*t=strtok_r(end+2," ", &save);
  unsigned field=3;
  while(t&&field<22){
    t=strtok_r(NULL," ",&save);
    field++;
  }
  require(t&&field==22,"stat-start");
  v.start=number(t);
  n=proc_read(x->pid,"status",b,sizeof b-1);
  b[n]=0;
  char *u=strstr((char *)b,"\nUid:\t"),*g=strstr((char *)b,"\nGid:\t");
  unsigned ids[4];
  require(u&&sscanf(u,"\nUid:\t%u\t%u\t%u\t%u",&ids[0],&ids[1],&ids[2],&ids[3])==4,"Uid");
  for(unsigned i=0;i<4;i++)require(ids[i]==1000,"Uid");
  require(g&&sscanf(g,"\nGid:\t%u\t%u\t%u\t%u",&ids[0],&ids[1],&ids[2],&ids[3])==4,"Gid");
  for(unsigned i=0;i<4;i++)require(ids[i]==1000,"Gid");
  uint64_t caught=status_signal_mask((char *)b,"\nSigCgt:\t");
  require((caught & (UINT64_C(1) << (SIGCONT-1))) != 0,"gate-CONT-handler-not-installed");
  v.blocked_signals=status_signal_mask((char *)b,"\nSigBlk:\t");
  require(strstr((char *)b,"\nThreads:\t1\n")!=NULL,"gate-not-single-threaded");
  char *np=strstr((char *)b,"\nNSpid:\t");
  require(np!=NULL,"NSpid");
  char *nl=strchr(np+1,'\n');
  require(nl!=NULL,"NSpid-end");
  *nl=0;
  char *last=np+strlen(np);
  while(last>np&&isdigit((unsigned char)last[-1]))last--;
  require(!strcmp(last,"1"),"not-private-PID1");
  char h[65];
  n=proc_read(x->pid,"cmdline",b,8192);
  digest(b,n,h);
  require(!strcmp(h,x->argv_sha)&&n&&b[n-1]==0,"argv-hash");
  const char *fixed[]={
    "/adhd-diagnostic/startup-gate","gate",x->nonce,"/usr/local/bin/elixir","elixir","-e"
  };
  size_t pos=0;
  for(unsigned i=0;i<6;i++){
    size_t k=strlen(fixed[i])+1;
    require(pos+k<=n&&!memcmp(b+pos,fixed[i],k),"gate-argv");
    pos+=k;
  }
  require(pos<n&&strnlen((char *)b+pos,n-pos)==n-pos-1&&!strcmp((char *)b+pos,original_serve),"SERVE-argv");
  n=proc_read(x->pid,"environ",b,65536);
  flags_ok(b,n);
  digest(b,n,h);
  require(!strcmp(h,x->env_sha),"ordered-environment-hash");
  char exe[64];
  snprintf(exe,sizeof exe,"/proc/%ld/exe",(long)x->pid);
  int ef=open(exe,O_RDONLY|O_CLOEXEC);
  require(ef>=0,"exe-open");
  struct stat st,after;
  require(fstat(ef,&st)==0&&S_ISREG(st.st_mode)&&st.st_size>0&&st.st_size<=1048576,"exe-size-type");
  Sha sha;
  init(&sha);
  unsigned char chunk[4096];
  size_t total=0;
  for(;;){
    ssize_t k=read(ef,chunk,sizeof chunk);
    if(k<0&&errno==EINTR)continue;
    require(k>=0,"exe-read");
    if(!k)break;
    total+=(size_t)k;
    require(total<=1048576,"exe-cap");
    add(&sha,chunk,(size_t)k);
  }
  finish(&sha,h);
  require(fstat(ef,&after)==0&&st.st_dev==after.st_dev&&st.st_ino==after.st_ino&&st.st_size==after.st_size&&total==(size_t)st.st_size&&!strcmp(h,x->gate_sha),"gate-exe-hash");
  close(ef);
  v.dev=st.st_dev;
  v.ino=st.st_ino;
  v.pidns=namespace_inode(x->pid,"pid");
  uint64_t observer_pidns=namespace_inode(getpid(),"pid");
  require(v.pidns!=observer_pidns,"observer-not-ancestor-PID-view");
  require_pid_ancestor(x->pid,v.pidns,observer_pidns);
  v.mntns=namespace_inode(x->pid,"mnt");
  v.cgns=namespace_inode(x->pid,"cgroup");
  v.timens=zero_time_namespace(x->pid);
  v.observer_timens=zero_time_namespace(getpid());
  expected_paths(x->cri_path,x->uid,x->cid,v.parent,v.child);
  n=proc_read(x->pid,"cgroup",b,sizeof b-1);
  b[n]=0;
  require(n>4&&!memcmp(b,"0::",3)&&b[n-1]=='\n'&&!memchr(b,'\n',n-1),"unified-cgroup-only");
  b[n-1]=0;
  require(!strcmp((char *)b+3,v.child),"live-cgroup-view-mismatch");
  strcpy(v.actual_cgroup,(char *)b+3);
  mount_view();
  n=proc_read(getpid(),"cgroup",b,sizeof b-1);
  b[n]=0;
  require(n>4&&!memcmp(b,"0::",3)&&b[n-1]=='\n'&&!memchr(b,'\n',n-1),"observer-unified-cgroup-only");
  b[n-1]=0;
  const char *self_path=(char *)b+3;
  size_t parent_length=strlen(v.parent);
  require(strncmp(self_path,v.parent,parent_length)!=0 ||
          (self_path[parent_length]!=0&&self_path[parent_length]!='/'),
          "observer-inside-Pod-budget");
  return v;
}
static int same(const Identity *a,const Identity *b){
  return a->start==b->start&&a->pidns==b->pidns&&a->mntns==b->mntns&&a->cgns==b->cgns&&a->timens==b->timens&&a->observer_timens==b->observer_timens&&a->dev==b->dev&&a->ino==b->ino&&!strcmp(a->actual_cgroup,b->actual_cgroup);
}
static int directory(const char *path){
  require(!strncmp(path,"/sys/fs/cgroup/",15),"directory-prefix");
  int fd=open("/sys/fs/cgroup",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  require(fd>=0,"cgroup-root");
  struct statfs fs;
  require(fstatfs(fd,&fs)==0&&fs.f_type==CGROUP2_MAGIC,"not-cgroup2");
  char copy[640];
  require(strlen(path)<sizeof copy,"directory-cap");
  strcpy(copy,path+15);
  char *save=NULL;
  for(char *p=strtok_r(copy,"/",&save);p;p=strtok_r(NULL,"/",&save)){
    require(strcmp(p,".")&&strcmp(p,".."),"directory-component");
    int next=openat(fd,p,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    close(fd);
    require(next>=0,"live-cgroup-directory-unavailable");
    fd=next;
    require(fstatfs(fd,&fs)==0&&fs.f_type==CGROUP2_MAGIC,"directory-filesystem");
  }
  return fd;
}
static const char *names[]={
  "memory.events","memory.events.local","memory.current","memory.max","memory.peak","pids.events","pids.current","pids.max","cgroup.events"
}
;
typedef struct {
  int fd,error;
  uint64_t dev,ino;
} Counter;
static Counter counters[2][9];
/* Namespace-root paths are not filesystem paths until joined to the verified
 * cgroup2 mount. Both scopes remain within this authenticated Pod. */
static void open_counters(const Identity *v){
  const char *paths[]={
    v->parent,v->child
  };
  for(unsigned j=0;j<2;j++){
    char absolute[768];
    require(snprintf(absolute,sizeof absolute,"/sys/fs/cgroup%s",paths[j])<(int)sizeof absolute,"cgroup-mount-join");
    int dir=directory(absolute);
    for(unsigned i=0;i<9;i++){
      Counter *c=&counters[j][i];
      c->fd=openat(dir,names[i],O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
      if(c->fd<0){
        c->error=errno;
        continue;
      }
      struct stat s;
      require(fstat(c->fd,&s)==0&&S_ISREG(s.st_mode),"counter-type");
      c->dev=s.st_dev;
      c->ino=s.st_ino;
    }
    close(dir);
  }
}
static void verify_memory_bound(void){
  Counter *c=&counters[1][3]; /* memory.max of the exact container, not parent. */
  require(c->fd>=0,"memory-max-unavailable");
  char raw[64];
  ssize_t n;
  do { n=pread(c->fd,raw,sizeof raw,0); } while(n<0&&errno==EINTR);
  require(n==10&&!memcmp(raw,"201326592\n",10),"memory-max-not-original192Mi");
}
static void json_counter(unsigned j,unsigned i){
  Counter *c=&counters[j][i];
  char out[4096],raw[1025];
  int err=c->error;
  ssize_t n=-1;
  if(c->fd>=0){
    do{
      n=pread(c->fd,raw,1024,0);
    }
    while(n<0&&errno==EINTR);
    if(n<0)err=errno;
    else if(n==0)err=ENODATA;
    else if(n==1024)err=EFBIG;
    else{
      for(ssize_t k=0;k<n;k++)require(isalnum((unsigned char)raw[k])||raw[k]=='_'||raw[k]==' '||raw[k]=='\t'||raw[k]=='\n',"counter-content");
    }
  }
  if(err){
    snprintf(out,sizeof out,"{\"scope\":\"%s\",\"file\":\"%s\",\"available\":false,\"errno\":%d}",j?"container":"pod",names[i],err);
    emit(out);
    return;
  }
  snprintf(out,sizeof out,"{\"scope\":\"%s\",\"file\":\"%s\",\"available\":true,\"dev\":%"PRIu64",\"ino\":%"PRIu64",\"text\":\"",j?"container":"pod",names[i],c->dev,c->ino);
  emit(out);
  for(ssize_t k=0;k<n;k++){
    char x[3]={
      raw[k],0,0
    }
    ;
    if(raw[k]=='\n'){
      x[0]='\\';
      x[1]='n';
    }
    if(raw[k]=='\t'){
      x[0]='\\';
      x[1]='t';
    }
    emit(x);
  }
  emit("\"}");
}
static void sample(unsigned seq, const struct pollfd *observed){
  char out[256];
  snprintf(out,sizeof out,"{\"kind\":\"sample\",\"sequence\":%u,\"monotonic_ns\":%"PRIu64",\"poll_revents\":[%d,%d,%d,%d,%d],\"counters\":[",seq,now_ns(),observed?observed[0].revents:0,observed?observed[1].revents:0,observed?observed[2].revents:0,observed?observed[3].revents:0,observed?observed[4].revents:0);
  emit(out);
  for(unsigned j=0;j<2;j++)for(unsigned i=0;i<9;i++){
    if(j||i)emit(",");
    json_counter(j,i);
  }
  emit("]}\n");
}
static void identity_json(const Input *x,const Identity *v){
  char out[2048];
  snprintf(out,sizeof out,"{\"kind\":\"gate-identity\",\"nonce\":\"%s\",\"pid\":%ld,\"kernel_state\":\"%c\",\"blocked_signals\":%"PRIu64",\"SIGCONT_handler_registered\":true,\"start_ticks\":%"PRIu64",\"pidns\":%"PRIu64",\"mntns\":%"PRIu64",\"cgroupns\":%"PRIu64",\"timens\":%"PRIu64",\"observer_timens\":%"PRIu64",\"timens_offsets_zero\":true,\"exe_dev\":%"PRIu64",\"exe_ino\":%"PRIu64",\"parent\":\"%s\",\"container\":\"%s\",\"deadline_ns\":%"PRIu64"}\n",x->nonce,(long)x->pid,v->state,v->blocked_signals,v->start,v->pidns,v->mntns,v->cgns,v->timens,v->observer_timens,v->dev,v->ino,v->parent,v->child,x->deadline);
  emit(out);
}
static volatile sig_atomic_t gate_released;
static void gate_continue(int signum) {
  (void)signum;
  gate_released=1;
}

static void gate(int argc,char **argv){
  require(argc==7&&hex(argv[2],32)&&!strcmp(argv[3],"/usr/local/bin/elixir")&&!strcmp(argv[4],"elixir")&&!strcmp(argv[5],"-e")&&!strcmp(argv[6],original_serve),"gate-arguments");
  require(getuid()==1000&&geteuid()==1000&&getgid()==1000&&getegid()==1000,"gate-UID");
  unsigned char env[65536];
  size_t n=0;
  for(char **p=environ;*p;p++){
    size_t k=strlen(*p)+1;
    require(k<=sizeof env-n,"gate-environment-cap");
    memcpy(env+n,*p,k);
    n+=k;
  }
  flags_ok(env,n);
  uint64_t gate_timens=zero_time_namespace(getpid());
  char h[65];
  digest(env,n,h);
  sigset_t cont_set, inherited_mask, waiting_mask, pending;
  require(sigemptyset(&cont_set)==0 && sigaddset(&cont_set,SIGCONT)==0,"gate-CONT-set");
  require(sigprocmask(SIG_BLOCK,&cont_set,&inherited_mask)==0,"gate-block-CONT");
  struct sigaction inherited_action={0}, action={0};
  action.sa_handler=gate_continue;
  require(sigemptyset(&action.sa_mask)==0 && sigaction(SIGCONT,&action,&inherited_action)==0,
          "gate-CONT-handler");
  require(sigpending(&pending)==0 && sigismember(&pending,SIGCONT)==0,"gate-unexpected-early-CONT");
  waiting_mask=inherited_mask;
  require(sigdelset(&waiting_mask,SIGCONT)==0,"gate-wait-unblocks-CONT");
  char out[512];
  int written=snprintf(out,sizeof out,"{\"kind\":\"gate-ready\",\"hold\":\"SIGCONT-handler-wait\",\"nonce\":\"%s\",\"pid\":%ld,\"ordered_env_sha256\":\"%s\",\"time_namespace_inode\":%"PRIu64",\"time_for_children_namespace_inode\":%"PRIu64",\"timens_offsets_zero\":true,\"monotonic_ns\":%"PRIu64",\"boottime_ns\":%"PRIu64"}\n",argv[2],(long)getpid(),h,gate_timens,gate_timens,now_ns(),boot_ns());
  require(written>=0&&(size_t)written<sizeof out,"gate-ready-output-cap");
  emit(out);
  while(!gate_released) {
    int result=sigsuspend(&waiting_mask);
    require(result==-1 && errno==EINTR,"gate-atomic-wait");
  }
  require(sigaction(SIGCONT,&inherited_action,NULL)==0,"gate-restore-CONT-disposition");
  require(sigprocmask(SIG_SETMASK,&inherited_mask,NULL)==0,"gate-restore-inherited-mask");
  execve(argv[3],argv+4,environ);
  fail("original-execve");
}
int main(int argc,char **argv){
  require(sizeof(void*)==8&&sizeof(off_t)==8,"64-bit-ABI");
  if(argc>=2&&!strcmp(argv[1],"gate")){
    gate(argc,argv);
    return 70;
  }
  require(argc==11||argc==14,"observer-arguments");
  require(getuid()==0&&geteuid()==0,"observer-owned-node-root-required");
  int inspect=!strcmp(argv[1],"inspect");
  require((inspect&&argc==11)||(!strcmp(argv[1],"observe")&&argc==14),"observer-mode");
  uint64_t pid=number(argv[2]);
  require(pid>1&&pid<=INT_MAX,"PID");
  Input x={
    (pid_t)pid,argv[3],argv[4],argv[5],argv[6],argv[7],argv[8],argv[9],number(argv[10])
  };
  require(uid_ok(x.uid)&&hex(x.cid,64)&&hex(x.nonce,32)&&hex(x.gate_sha,64)&&hex(x.argv_sha,64)&&hex(x.env_sha,64),"observer-identifiers");
  uint64_t start=now_ns();
  require(x.deadline>start&&x.deadline-start<=30*NS,"original-Ready30-deadline");
  int flags=fcntl(1,F_GETFL);
  require(flags>=0&&fcntl(1,F_SETFL,flags|O_NONBLOCK)==0,"nonblocking-output");
  Identity first=identity(&x,'W');
  identity_json(&x,&first);
  if(inspect)return 0;
  require(first.start==number(argv[11])&&first.pidns==number(argv[12])&&first.mntns==number(argv[13]),"preinspected-identity");
  int pfd=(int)syscall(SYS_pidfd_open,x.pid,0);
  require(pfd>=0,"pidfd-open");
  Identity second=identity(&x,'W');
  require(same(&first,&second),"identity-changed");
  struct pollfd life={
    pfd,POLLIN,0
  };
  require(poll(&life,1,0)==0,"process-not-live");
  require(now_ns()+20*NS<x.deadline,"STOP-not-within-original-first10seconds");
  require(syscall(SYS_pidfd_send_signal,pfd,SIGSTOP,NULL,0)==0,"ancestor-pidfd-STOP");
  wait_for_kernel_stop(&x,pfd);
  Identity stopped=identity(&x,'T');
  require(same(&second,&stopped),"identity-after-actual-STOP");
  identity_json(&x,&stopped);
  emit("{\"kind\":\"ancestor-stop\",\"signal\":\"pidfd-SIGSTOP\",\"kernel_state\":\"T\",\"actual_stop_proven\":true}\n");
  open_counters(&stopped);
  verify_memory_bound();
  sample(0, NULL);
  Identity third=identity(&x,'T');
  require(same(&stopped,&third),"identity-before-CONT");
  require(now_ns()+20*NS<=x.deadline,"release-not-within-first10seconds");
  require(syscall(SYS_pidfd_send_signal,pfd,SIGCONT,NULL,0)==0,"pidfd-CONT");
  emit("{\"kind\":\"released\",\"signal\":\"pidfd-SIGCONT\",\"environment_rewritten\":false}\n");
  unsigned seq=1;
  int died=0;
  while(now_ns()<x.deadline&&seq<MAX_SAMPLES){
    struct pollfd pf[5]={
      {
        pfd,POLLIN,0
      }
      ,{
        counters[0][0].fd,POLLPRI|POLLERR,0
      }
      ,{
        counters[0][1].fd,POLLPRI|POLLERR,0
      }
      ,{
        counters[1][0].fd,POLLPRI|POLLERR,0
      }
      ,{
        counters[1][1].fd,POLLPRI|POLLERR,0
      }
    }
    ;
    uint64_t current=now_ns();
    if(current>=x.deadline)break;
    uint64_t rem=x.deadline-current;
    int ms=(int)(rem/1000000);
    if(ms>200)ms=200;
    if(ms<0)ms=0;
    int r=poll(pf,5,ms);
    if(r<0&&errno==EINTR)continue;
    require(r>=0,"counter-poll");
    sample(seq++, pf);
    /* Read parent then child before reporting simultaneous PID death. */
    if(pf[0].revents&(POLLIN|POLLHUP|POLLERR)){
      died=1;
      break;
    }
  }
  require(seq<MAX_SAMPLES,"sample-cap");
  for(unsigned j=0;j<2;j++)for(unsigned i=0;i<9;i++)if(counters[j][i].fd>=0)close(counters[j][i].fd);
  close(pfd);
  char out[256];
  snprintf(out,sizeof out,"{\"kind\":\"complete\",\"process_death_observed\":%s,\"Ready30_deadline_reached\":%s,\"samples\":%u,\"cause\":\"not-inferred\"}\n",died?"true":"false",died?"false":"true",seq);
  emit(out);
  return 0;
}
