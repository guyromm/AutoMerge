#!/usr/bin/env python
from automerge import getstatusoutput,AutoMerger,add_common_args,cd
import os,re
import config as c
import argparse

# scenarios, edge cases
# a. some parent modules do not have branch
# b. some child modules do not have branch
# c. source branch masks

        
def perform(args,am):
        tocommit={};notcloned=[] ; havecloned={} ; already_in = {}
        for r in args.repos[0]:
                tocommit,already_in,notcloned,havecloned = perform_one(args,am,r,havecloned,tocommit,already_in,notcloned,args.branch,args.push)
        
        if not len(tocommit):
                print('NOTHING TO COMMIT!')
        # 4. commit affected
        for rrepo,items in tocommit.items():
                print('ABOUT TO COMMIT',rrepo,items)
                commit_repo(rrepo,items)
                # 5. push if required
                tbranch = [i[1] for i in items][0]
                if args.push:
                        push_repo(rrepo,tbranch)
        for rrepo,items in already_in.items():
                print('ALREADY_IN',rrepo,items)
                
        if len(notcloned):
                print('NOT CLONED:')
                print('\n'.join(['/'.join(nc) for nc in notcloned]))
        

        
def perform_one(args,am,repo,havecloned,tocommit,already_in,notcloned,branch,push=False):
        # 1. understand which parent repos contain the affected repos as submodules
        dorepos = [[r,c.SUBMODULES[r]] for r in c.REPOS \
                   if repo in [sm['repo'] for sm in c.SUBMODULES.get(r,[])]]
        target_repos = args.target_repos and args.target_repos.split(',') or []
        if len(target_repos):
                dorepos = [dr for dr in dorepos if dr in target_repos]

        # 2. obtain revs of specified repo on branch
        if len(dorepos):
                assert am.clone(repo,branches=[branch]),"could not clone %s"%repo
                assert am.checkout(repo,branch),"could not check out %s on %s"%(branch,repo)
                rd = os.path.join(c.REPODIR,repo)
                with cd(rd):
                        st,rev = getstatusoutput("git log -1 --pretty=oneline | awk '{print $1}'")
                        assert st==0
                        rev = rev.strip()
        else:
                print('NOT CLONING AFFECTED REPO - dorepos is empty.')

        # 3. perform the replacement
        for rr in dorepos:
                if len(target_repos) and rr[0] not in target_repos:
                        #print('EXPLICITLY SKIPPING',rr[0])
                        continue
                # [sm for sm in c.SUBMODULES[r] if sm['repo']==r]
                # raise Exception('setting',repo,'to',rev,'on',dorepos)
                rrepo = rr[0]
                rsubs = [rsub for rsub in rr[1] if rsub['repo']==repo]
                for rsub in rsubs:
                        # if source submodule has its branch under a target_branch_mask scheme
                        # do a reverse lookup of the original branch on the target
                        # to figure out which branch target repos to commit to.
                        tbm=rsub.get('target_branch_mask','') ; target_branch=None
                        if tbm:
                                sbm = '^'+tbm.replace('%s','(.*)')+'$' # FIXME: ugly and bad.
                                tbres = re.compile(sbm).search(branch)
                                if tbres:
                                        target_branch = tbres.group(1)
                                        print('TARGET_BRANCH matched from reverse mask',sbm,':',branch,'=>',target_branch)
                                else:
                                        if branch in c.TOP_LEVEL_BRANCHES:
                                                print('TARGET_BRANCH failed to match from mask; is A TOP LEVEL; skipping',target_branch,sbm)
                                                continue
                                        else:
                                                target_branch = branch
                                                print('TARGET_BRANCH failed to match from mask; is not top-level. using source branch',branch)  
                                                
                        else:
                                target_branch = branch
                                print('TARGET_BRANCH vanilla, without mask mask',target_branch)
                        assert target_branch,"target branch not set"
                        
                        rrepo in havecloned or am.clone(rrepo,branches=[target_branch])
                        if rrepo in havecloned or am.checkout(rrepo,target_branch):
                                if havecloned.get(rrepo): assert havecloned[rrepo]==target_branch,"%s != %s for havecloned %s"%(havecloned[rrepo],target_branch,rrepo)
                                if rrepo not in havecloned: havecloned[rrepo]=target_branch
                                # make sure we are on the right branch
                                br = am.get_current_branch(rrepo)
                                assert br==target_branch,"%s of %s != %s"%(br,rrepo,target_branch)
                                if update_index(am,rrepo,rsub['path'],rev):
                                        if rrepo not in tocommit: tocommit[rrepo]=[]
                                        tocommit[rrepo].append(["%s/%s:%s"%(repo,branch,rev),target_branch])
                                else:
                                        if rrepo not in already_in: already_in[rrepo]=[]                                        
                                        already_in[rrepo].append("%s/%s:%s"%(repo,branch,rev))
                        else:
                                print('COULD NOT CLONE/CHECKOUT',rrepo,target_branch,'; SKIPPING')
                                notcloned.append([rrepo,target_branch])
        return tocommit,already_in,notcloned,havecloned


def commit_repo(repo,items):
        rd = os.path.join(c.REPODIR,repo)
        tbranches = set([i[1] for i in items])
        assert len(tbranches)==1,"not a single target branch per repo for %s? %s"(repo,tbranches)
        
        with cd(rd):
                cmd = 'git commit -m "submodule_sync of %s"'%",".join([i[0] for i in items])
                #print('executing',cmd,'in',rd)
                st,op = getstatusoutput(cmd)
                if st!=0: print('commit returned',st,'output',op)
                assert st==0,op

def push_repo(repo,branch):
        rd = os.path.join(c.REPODIR,repo)
        with cd(rd):
                cmd = 'git push origin %s'%branch
                st,op = getstatusoutput(cmd)
                assert st==0
                
def update_index(am,repo,path,rev):
        rd = os.path.join(c.REPODIR,repo)
        with cd(rd):
                st,op = getstatusoutput("git ls-tree HEAD -- %s | awk '{print $3}'"%path)
                assert st==0
                crev = op.strip()
                if crev==rev:
                        print('%s ALREADY SET on %s %s'%(rev,repo,path))
                        return False
                cmd = 'git update-index --cacheinfo 160000 %s %s'%(rev,path)
                st,op = getstatusoutput(cmd)
                print('HAVE UPDATED INDEX ON %s/%s to %s'%(repo,path,rev)) 
                assert st==0,"%s returned %s\n%s\n in %s"%(cmd,st,op,rd)
        return True

if __name__=='__main__':
        optparser = argparse.ArgumentParser(
            description='merge branches across multiple repos with a '
                        'single commit.',
            add_help=True)
        optparser.add_argument(
            '--branch', action='store', dest='branch', help='branch to match',
            required=False)

        add_common_args(optparser)

        optparser.add_argument('--target-repos',
                               action='store',
                               dest='target_repos',
                               help='Comma separated list of target repositories to limit to. Default is any repo with touched submodule(s) defined in SUBMODULES.')
        
        optparser.add_argument(
            'repos',action='append',nargs='*')
    
        args = optparser.parse_args()
        am = AutoMerger()
        am.setargs(args)
        perform(args,am)
