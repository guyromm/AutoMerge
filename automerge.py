#!/usr/bin/env python
from commands import getstatusoutput
import argparse,os
import config as c

def gso(repo,cmd):
    repodir = os.path.join(c.REPODIR,repo)
    assert os.path.exists(repodir)
    cmd = 'cd %s && %s'%(repodir,cmd)
    return getstatusoutput(cmd)
#make sure no extra files are merged
#make sure that the source branch has all the commits of the target branch 
class AutoMerger(object):
    def __init__(self):
        self.repos = self.get_repos()
    def setargs(self,args):
        self.args = args
    def get_repos(self):
        myrepos = c.REPOS
        retrepos={}
        for repo in myrepos:
            if ':/' not in repo:
                nrepo=c.DEFAULT_HOST+":/"+repo
                retrepos[repo]=nrepo
        return retrepos
    def clone(self,repo):
        fqdn = self.repos[repo]
        repopath = os.path.join(c.REPODIR,repo)
        if self.args.purge and os.path.exists(repopath):
            st,op = getstatusoutput("rm -rf %s"%repopath) ; assert st==0
            print '%s purged.'%repo
        if not self.args.noclone and not os.path.exists(repopath):
            print 'initial clone of %s.'%(repo)
            cmd = 'cd %s && git clone %s'%(c.REPODIR,fqdn)
            st,op = getstatusoutput(cmd)
            assert st==0,"%s returned %s: %s"%(cmd,st,op)
            print 'clone complete.'
        elif not self.args.nofetch:
            print 'fetch -a of %s'%repo
            cmd = 'git fetch -a'
            st,op = gso(repo,cmd) ; assert st==0,"%s returned %s"%(cmd,st)
            print 'fetch -a complete.'
    def checkout(self,repo,branch):
        #print 'checkout of %s/%s'%(repo,branch)
        cmd = 'git checkout {branch} '.format(repo=repo,branch=branch)
        if not self.args.nopull: cmd+= '; git pull origin {branch}'.format(repo=repo,branch=branch)

        st,op = gso(repo,cmd) ; assert st in [0,256],"%s returned %s"%(cmd,st)
        if st==256:
            print '%s does not have branch %s'%(repo,branch)
            return False
        return True
        #print 'checkout complete.'
    def get_current_branch(self,repo):
        cmd = 'git branch | grep "^*"'
        st,op = gso(repo,cmd) ; assert st==0
        curbranch = op.split('* ')[1].split('\n')[0]
        return curbranch
    def get_last_commits(self,repo,branch,commits=1,with_message=False):
        assert self.get_current_branch(repo)==branch
        cmd = 'git log --pretty=oneline | head -{commits}'.format(repo=repo,commits=commits)
        st,op = gso(repo,cmd); assert st==0
        commits=[]
        for ln in op.split('\n'):
            if with_message:
                spl = ln.split(' ')
                commitid = spl[0]
                message = ' '.join(spl[1:])
                apnd = {'rev':commitid,'message':message}
            else:
                apnd = ln.split(' ')[0]
            commits.append(apnd)

        return commits
    def got_untracked(self,repo):
        cmd = 'git status'.format(repo=repo)
        st,op = gso(repo,cmd) ; assert st==0
        if 'Untracked files' in op:
            print 'repo {repo} has untracked files in branch {branch}'.format(repo=repo,branch=self.get_current_branch(repo))
            print '\n'.join(op.split('Untracked files:')[1].split('\n')[3:])
            return True
        else:
            return False
    def handle_submodules(self,repo,to_branch):
        results=[]
        if repo not in c.SUBMODULES: return
        submodules = c.SUBMODULES[repo]
        for sm in submodules:
            print 'handling submodule %s'%sm
            smpath = os.path.join(c.REPODIR,repo,sm['path'])
            smdir = os.path.dirname(smpath)
            bn = os.path.basename(smpath)
            cwd = os.getcwd()
            localsource = os.path.join(cwd,c.REPODIR,sm['repo'])
            #print 'inspecting %s'%smpath
            assert os.path.isdir(smpath) ; 
            st,op = getstatusoutput('ls %s'%smpath) ; assert st==0 
            assert len(op.split("\n"))<2
            formatargs = {'smpath':smpath,'smdir':smdir,'localsource':localsource,'basename':bn,'target_branch':to_branch}
            cmd1 = 'cd {smdir} && rm -rf {basename} && git clone {localsource} {basename} && cd {basename}'.format(**formatargs)
            st,op = getstatusoutput(cmd1) ; assert st==0,"%s returned %s: %s"%(cmd1,st,op)
            cmd2 = 'cd {smpath} && git checkout {target_branch}'.format(**formatargs)
            st,op = getstatusoutput(cmd2) ; assert st in [0,256],"%s returned %s: %s"%(cmd2,st,op)
            if st==256:
                print 'looks like %s does not have our branch %s. reverting'%(sm['path'],to_branch)
                cmd3 = "cd {smdir} && rm -rf {basename} && mkdir {basename}".format(**formatargs)
                st,op = getstatusoutput(cmd3) ; assert st==0
            else:
                print 'SUCCESFULLY UPDATED %s (%s) to branch %s'%(sm['repo'],sm['path'],to_branch)
                results.append(sm)
        return results    
    completed=[]
    screwed_up=[]
    def single_merge(self,repo,from_branch,to_branch,lastcommits,message):
        print 'commencing single merge %s => %s.'%(from_branch,to_branch)
        self.checkout(repo,to_branch)
        cmd = 'git merge {source_branch}'.format(repo=repo,source_branch=from_branch)
        st,op = gso(repo,cmd) ; assert st==0
        target_last_commit = lastcommits[to_branch][0]
        print 'regular merge done. resetting to last %s commit %s'%(to_branch,target_last_commit)
        if self.got_untracked(repo): raise Exception('got untracked files in single merge.')
        cmd = 'git reset {target_last_commit}'.format(repo=repo,target_last_commit=target_last_commit)
        st,op = gso(repo,cmd) ; assert st==0

        sm_updated = self.handle_submodules(repo,to_branch)
        
        print 'reset succesful.'
        cmd = 'git add . && git add -u'.format(repo=repo)
        print 'running %s'%cmd
        st,op = gso(repo,cmd) ; assert st==0
        print 'added all files and deletions for commit.'
        cmd = 'git commit -m "{message}"'.format(repo=repo,message=message)
        st,op = gso(repo,cmd) ; assert st==0
        print 'succesfully re-merged.'
        cmd = 'git push origin {target_branch}'.format(repo=repo,target_branch=to_branch)
        if self.args.nopush:
            print '#please execute in %s:'%repo
            print cmd
            torun='cd %s && '%(os.path.join(c.REPODIR,repo))+cmd
        if self.args.push:
            st,op = gso(repo,cmd); assert st==0
            torun=None
        return {'torun':torun,'sm_updated':sm_updated}
    aborted=[]
    def merge(self,repo,from_branch,to_branch,message):
        print 'WORKING MERGE on %s %s => %s'%(repo,from_branch,to_branch)
        assert repo in self.repos
        self.clone(repo)

        lastcommits={}
        for br in [from_branch,to_branch]:
            if not self.checkout(repo,br):
                self.aborted.append({'repo':repo,'source_branch':from_branch,'target_branch':to_branch,'reason':'initial checkout failed.'})
                return
            lastcommits[br]=self.get_last_commits(repo,br,commits=10)

        self.checkout(repo,from_branch)
        if self.got_untracked(repo):
            raise Exception('has untracked files.')
        target_last_commit = lastcommits[to_branch][0]
        source_last_commit = lastcommits[from_branch][0]
        if target_last_commit not in lastcommits[from_branch]:
            print 'target branch ({target_branch}) last commit {target_last_commit} is not present in source branch {source_branch}'\
                .format(target_branch=to_branch,
                        source_branch=from_branch,
                        target_last_commit=target_last_commit)
            self.checkout(repo,to_branch)
            last_commit_w_msg = self.get_last_commits(repo,to_branch,1,True)[0]
            if last_commit_w_msg['message']==message:
                self.aborted.append({'repo':repo,'source_branch':from_branch,'target_branch':to_branch,'reason':'Already merged.'})
                return
            print 'last commits on %s'%from_branch
            print lastcommits[from_branch]
            self.aborted.append({'repo':repo,'source_branch':from_branch,'target_branch':to_branch,'reason':'Missing last target commit on source.'.upper()})
            return
        if target_last_commit==source_last_commit:
            raise Exception( 'WARNING: branches %s and %s are identical.'%(from_branch,to_branch))
        try:
            rt = self.single_merge(repo,from_branch,to_branch,lastcommits,message)
            torun = rt['torun'] ; sm_updated = rt['sm_updated']
            rev = self.get_last_commits(repo,to_branch,1)[0]
            self.completed.append({'repo':repo,'source_branch':from_branch,'target_branch':to_branch,'torun':torun,'rev':rev,'submodules_updated':sm_updated})
        except Exception,e:
            self.screwed_up.append({'repo':repo,'source_branch':from_branch,'target_branch':to_branch,'error':str(e)})

    @staticmethod
    def _sortaborted(e1,e2):
        return cmp(e1['reason'],e2['reason'])
    def print_results(self):
        if len(self.completed):
            print '########## COMPLETE: ##########'
            for res in self.completed: print res
        self.aborted.sort(self._sortaborted)
        if len(self.aborted):
            print '########## ABORTED: ##########'
            for abrt in self.aborted: print abrt
        if len(self.screwed_up):
            print '########## SCREWED UP: ##########'
            for scr in self.screwed_up: print scr

    def cmdrun(self):
        optparser = argparse.ArgumentParser(description='merge branches across multiple repos with a single commit.', add_help=True)
        optparser.add_argument('--from', action='store', dest='from_branch',help='source branch')
        optparser.add_argument('--to', action='store', dest='to_branch',help='target branch')
        optparser.add_argument('--message', action='store', dest='message',help='commit message for the merge commit')
        optparser.add_argument('--repo', action='append', dest='repos',help='specify specific repository(ies) to merge. repeatable.')
        optparser.add_argument('--nofetch',action='store_true',dest='nofetch',help='do not run git fetch -a')
        optparser.add_argument('--nopull',action='store_true',dest='nopull',help='do not pull latest branches, use the ones that exist locally.')
        optparser.add_argument('--noclone',action='store_true',dest='noclone',help='avoid cloning missing repositories.')
        optparser.add_argument('--nopush',action='store_true',dest='nopush',help='do not push - the default.')
        optparser.add_argument('--push',action='store_true',dest='push',help='push to origin after merge is done locally.')
        optparser.add_argument('--allrepos',action='store_true',dest='allrepos',help='merge all repositories instead of specifying via --repo')
        optparser.add_argument('--purge',action='store_true',dest='purge',help='purge all locally cached repos.')
        args = optparser.parse_args()

        self.setargs(args)

        if args.allrepos:
            dorepos = c.REPOS
        else:
            dorepos = args.repos
        for repo in dorepos:
            self.merge(repo,args.from_branch,args.to_branch,args.message)
        self.print_results()

if __name__ == '__main__':
    # init and run parser
    m = AutoMerger()
    m.cmdrun()


