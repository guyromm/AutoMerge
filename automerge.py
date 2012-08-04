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
    def __init__(self,args):
        self.repos = self.get_repos()
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
        if not self.args.noclone and not os.path.exists(repo):
            print 'initial clone of %s.'%(repo)
            cmd = 'cd %s && git clone %s'%(c.REPODIR,fqdn)
            st,op = getstatusoutput(cmd)
            assert st==0
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
        st,op = gso(repo,cmd) ; assert st==0,"%s returnde %s"%(cmd,st)
        #print 'checkout complete.'
    def get_current_branch(self,repo):
        cmd = 'git branch | grep "^*"'%(repo)
        st,op = gso(repo,cmd) ; assert st==0
        curbranch = op.split('* ')[1].split('\n')[0]
        return curbranch
    def get_last_commits(self,repo,branch,commits=1):
        assert self.get_current_branch(repo)==branch
        cmd = 'git log --pretty=oneline | head -{commits}'.format(repo=repo,commits=commits)
        st,op = gso(repo,cmd); assert st==0
        commits=[]
        for ln in op.split('\n'):
            commitid = ln.split(' ')[0]
            commits.append(commitid)

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
            print '#please execute:'
            print cmd
        if self.args.push:
            st,op = gso(repo,cmd); assert st==0

    def merge(self,repo,from_branch,to_branch,message):
        assert repo in self.repos
        self.clone(repo)

        lastcommits={}
        for br in [from_branch,to_branch]:
            self.checkout(repo,br)
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
            raise Exception('missing last target commit on source.')
        if target_last_commit==source_last_commit:
            raise Exception( 'WARNING: branches %s and %s are identical.'%(from_branch,to_branch))
        self.single_merge(repo,from_branch,to_branch,lastcommits,message)
    
if __name__ == '__main__':
    optparser = argparse.ArgumentParser(
        description='AutoMerger one commit merge', add_help=True)
    
    optparser.add_argument('--from', action='store', dest='from_branch',
                           help='source branch')

    optparser.add_argument('--to', action='store', dest='to_branch',
                           help='target branch')

    optparser.add_argument('--message', action='store', dest='message',
                           help='merge commit message')

    optparser.add_argument('--repo', action='append', dest='repos',
                           help='specific repositories to merge.'
                           )
    optparser.add_argument('--nofetch',action='store_true',dest='nofetch',help='do not fetch -a')
    optparser.add_argument('--nopull',action='store_true',dest='nopull',help='do not pull latest branches')
    optparser.add_argument('--noclone',action='store_true',dest='noclone',help='do not clone')
    optparser.add_argument('--nopush',action='store_true',dest='nopush',help='do not push')
    optparser.add_argument('--push',action='store_true',dest='push',help='push to origin')
    optparser.add_argument('--allrepos',action='store_true',dest='allrepos',help='merge all repositories.')
    args = optparser.parse_args()

    # init and run parser
    m = AutoMerger(args)

    if args.allrepos:
        dorepos = c.REPOS
    else:
        dorepos = args.repos
    for repo in dorepos:
        m.merge(repo,args.from_branch,args.to_branch,args.message)


