#!/usr/bin/env python
from commands import getstatusoutput
import argparse
import json
import os
import re
import sys
import config as c


def gso(repo=None, cmd=None, path=None):
    if repo is not None:
        repodir = os.path.join(c.REPODIR, repo)
        assert os.path.exists(repodir),"%s does not exist"%(repodir)
        cmd = 'cd %s && %s' % (repodir, cmd)
    elif path is not None:
        cmd = 'cd %s && %s' % (path, cmd)
    assert cmd is not None
    return getstatusoutput(cmd)
#make sure no extra files are merged
#make sure that the source branch has all the commits of the target branch


class AutoMerger(object):

    def __init__(self):
        self.repos = self.get_repos()

    def setargs(self, args):
        self.args = args

    def get_repos(self):
        myrepos = c.REPOS
        retrepos = {}
        for repo in myrepos:
            if ':/' not in repo:
                nrepo = c.DEFAULT_HOST + ":/" + repo
                retrepos[repo] = nrepo
        return retrepos

    def clone(self, repo, branches=[]):
        fqdn = self.repos[repo]
        repopath = os.path.join(c.REPODIR, repo)
        cachedir = os.path.join(c.CACHEDIR, repo)
        if self.args.purge and os.path.exists(repopath):
            st, op = getstatusoutput("rm -rf %s" % repopath)
            assert st == 0
            print '%s purged.' % repo
        if self.args.purge_cache and os.path.exists(cachedir):
            st, op = getstatusoutput("rm -rf %s" % cachedir)
            assert st == 0
            print '%s purged.' % repo
        if not os.path.exists(cachedir):
            print 'initial clone of %s into CACHE.' % (repo)
            cmd = 'cd %s && git clone %s' % (c.CACHEDIR, fqdn)
            st, op = getstatusoutput(cmd)
            assert st == 0, "%s returned %s: %s" % (cmd, st, op)
            print 'clone complete.'
        elif os.path.exists(cachedir):
            for branch in set(branches):
                print 'resetting cache %s to remote %s.'%(cachedir,branch)
                if len(branch)==40:
                    prefix=''
                else:
                    prefix='origin/'
                cmd = 'cd %(cachedir)s && git fetch -a && git checkout %(branch)s && git clean -f -d ; git reset --hard %(prefix)s%(branch)s'%{'cachedir':cachedir,'branch':branch,'prefix':prefix}
                st,op =getstatusoutput(cmd) ; assert st==0,"%s returned %s\n%s"%(cmd,st,op)

        if not self.args.noclone and not os.path.exists(repopath):
            print 'clone of %s.' % (repo)
            cmd = 'cd %s && ../git-new-workdir %s %s' % (c.REPODIR,os.path.join('..',cachedir),repo)
            st, op = getstatusoutput(cmd)
            assert st == 0, "%s returned %s: %s" % (cmd, st, op)
            print 'clone complete.'
        elif not self.args.nofetch:
            print 'fetch -a of %s' % repo
            cmd = 'git fetch -a'
            st, op = gso(repo, cmd)
            assert st == 0, "%s returned %s" % (cmd, st)
            print 'fetch -a complete.'
       
    def checkout(self, repo, branch):
        if len(branch)==40:
            prefix='--detach'
        else:
            prefix=''
        cmd = 'git checkout {prefix} {branch} '.format(prefix=prefix,repo=repo, branch=branch)

        if len(branch)!=40 and not self.args.nopull:
            cmd += '; git pull origin {branch}'.format(
                repo=repo, branch=branch)

        st, op = gso(repo, cmd)
        assert st in [0, 256], "%s returned %s" % (cmd, st)
        if st == 256:
            print '%s does not have branch %s' % (repo, branch)
            return False
        return True

    def get_current_branch(self, repo):
        cmd = 'git branch | grep "^*"'
        st, op = gso(repo, cmd)
        assert st == 0
        curbranch = op.split('* ')[1].split('\n')[0]
        return curbranch

    def get_last_commits(self, repo, branch, commits=1, with_message=False, path=False):
        if not path:
            curbranch = self.get_current_branch(repo)
            if len(branch)!=40:
                assert curbranch == branch,"%s <> %s"%(curbranch,branch)
            assert repo
            assert branch
            pathgo = None
        else:
            pathgo = path
        cmd = 'git log --pretty=oneline --no-color| head -{commits}'.format(
            repo=repo, commits=commits)
        st, op = gso(repo, cmd, path=pathgo)
        assert st == 0
        commits = []
        for ln in op.split('\n'):
            if with_message:
                spl = ln.split(' ')
                commitid = spl[0]
                message = ' '.join(spl[1:])
                apnd = {'rev': commitid, 'message': message}
            else:
                apnd = ln.split(' ')[0]
            commits.append(apnd)
        return commits

    def got_untracked(self, repo):
        cmd = 'git status'.format(repo=repo)
        st, op = gso(repo, cmd)
        assert st == 0
        if 'Untracked files' in op:
            print 'repo {repo} has untracked files in branch {branch}'.format(
                repo=repo, branch=self.get_current_branch(repo))
            print '\n'.join(op.split('Untracked files:')[1].split('\n')[3:])
            return True
        else:
            return False

    def handle_submodules(self, repo, to_branch):
        results = []
        if repo not in c.SUBMODULES:
            print '%s not in %s. skipping submodules' % (repo, c.SUBMODULES)
            return
        submodules = c.SUBMODULES[repo]
        print 'working through submodules %s' % submodules
        for sm in submodules:
            if sm['repo'] not in self.completed_lst:
                print 'skipping submodule %s,'\
                      'as it is not touched by this merge.' % sm['repo']
                continue
            print 'handling submodule %s' % sm
            smpath = os.path.join(c.REPODIR, repo, sm['path'])
            smdir = os.path.dirname(smpath)
            bn = os.path.basename(smpath)
            cwd = os.getcwd()
            localsource = os.path.join(cwd, c.REPODIR, sm['repo'])
            #print 'inspecting %s'%smpath

            assert os.path.isdir(smpath), "%s is not a directory" % smpath
            st, op = getstatusoutput('ls %s' % smpath)
            assert st == 0
            assert len(op.split("\n")) < 2, "bad length of\n%s" % op
            formatargs = {
                'smpath': smpath,
                'smdir': smdir,
                'localsource': localsource,
                'basename': bn,
                'target_branch': to_branch,
            }

            cmd1 = 'cd {smdir} && rm -rf {basename} '\
                   '&& git clone {localsource} {basename} '\
                   '&& cd {basename}'.format(**formatargs)
            st, op = getstatusoutput(cmd1)
            assert st == 0, "%s returned %s: %s" % (cmd1, st, op)
            cmd2 = 'cd {smpath} '\
                   '&& git checkout {target_branch}'.format(**formatargs)
            st, op = getstatusoutput(cmd2)
            assert st in [0, 256], "%s returned %s: %s" % (cmd2, st, op)
            if st == 256:
                print 'looks like %s does not have our branch %s. '\
                      'reverting' % (sm['path'], to_branch)
                cmd3 = "cd {smdir} && rm -rf {basename} "\
                       "&& mkdir {basename}".format(**formatargs)
                st, op = getstatusoutput(cmd3)
                assert st == 0
            else:
                print 'SUCCESFULLY UPDATED %s (%s) to branch %s'\
                      % (sm['repo'], sm['path'], to_branch)
                sm['new_rev'] = self.get_last_commits(
                    repo=None, branch=None, commits=1, path=smpath)[0]
                results.append(sm)
        return results
    completed = []
    completed_lst = []
    screwed_up = []

    def single_merge(
            self, merge_type, repo, from_branch, to_branch, lastcommits, message):
        return self.perform_merge(
            'single', repo, from_branch, to_branch, lastcommits, message)

    def standard_merge(
            self, merge_type, repo, from_branch, to_branch, lastcommits, message):
        return self.perform_merge(
            'standard', repo, from_branch, to_branch, lastcommits, message)

    def none_merge(
            self, merge_type, repo, from_branch, to_branch, lastcommits, message):
        print 'none_merge on %s/%s: not doing anything' % (repo, from_branch)
        return {'torun': None, 'sm_updated': None, 'conflicts': None}

    confre = re.compile(
        '^CONFLICT \((?P<conflict_type>.*)\): (?P<conflict_message>.*)$')

    def extract_conflicts(self, op):
        rt = []
        for line in op.split('\n'):
            cres = self.confre.search(line)
            if not cres:
                assert 'CONFLICT' not in line
            if cres:
                fname = cres.group('conflict_message').split(' in ')[1]
                rt.append(
                    {'type': cres.group('conflict_type'),
                     'message': cres.group('conflict_message'),
                     'fname': fname})
        return rt

    def get_diff_files(self, repo,withbranch=None):
        cmd = 'git diff --name-only'
        if withbranch: cmd+=' %s'%withbranch
        st, op = gso(repo, cmd)
        #print op
        rt=[]
        if st == 0:
            rt+= op.split('\n')
        cmd = 'git ls-files --other --exclude-standard'
        st,op = gso(repo,cmd)
        if st ==0:
            rt+= op.split('\n')
        return set(rt)

    def run_linters(self, repo,withbranch=None):
        output = {}
        ofns = {}
        for cmd in ['jshint','pyflakes','pep8']:
            ofns[cmd]='%s-%s.log'%(repo,cmd)
            if os.path.exists(ofns[cmd]): os.unlink(ofns[cmd])
        dfiles = self.get_diff_files(repo,withbranch=withbranch)
        print('%s diff files'%len(dfiles))
        for file2check in dfiles:
            if not os.path.exists(os.path.join(c.REPODIR,repo,file2check)): continue
            if file2check.endswith('.js'):
                cmd='jshint'
                mycmd = 'jshint %s'%file2check
                print mycmd
                st,op = gso(repo,mycmd) #; assert st in [0,256],"%s returned %s"%(mycmd,st)

                lines = [ln for ln in op.split('\n')[0:-1] if ln!='']
                ofn = ofns[cmd]
                ofp = open(ofn,'a') ; ofp.write('\n'.join(lines)+'\n') ; ofp.close()
                if cmd not in output: output[cmd]=0
                output[cmd]+=len(lines)

            if file2check.endswith('.py'):
                for cmd in ['pep8', 'pyflakes']:
                    mycmd = cmd + ' ' + file2check
                    print mycmd
                    st, op = gso(repo, mycmd) #; assert st in [0,256],"%s returned %s"%(mycmd,st)
                    if st == 256:
                        ofn = ofns[cmd]
                        ofp = open(ofn,'a') ; ofp.write(op+'\n') ; ofp.close()
                        if cmd not in output: output[cmd]=0
                        output[cmd]+=len(op.split('\n'))
        return output
        #if output: sys.exit(output)

    def perform_merge(
            self, merge_type, repo, from_branch, to_branch, lastcommits, message):
        print 'commencing %s merge %s => %s.'\
              % (merge_type, from_branch, to_branch)
        self.checkout(repo, to_branch)
        cmd = 'git merge {source_branch}'.format(
            repo=repo, source_branch=from_branch)
        st, op = gso(repo, cmd)

        #in standard merges we are explicit about conflicts
        conflicts = None
        if merge_type == 'standard' and st == 256:
            print 'standard merge returned %s' % st
            conflicts = self.extract_conflicts(op)
            raise Exception('got confl')
        else:
            assert st == 0, "%s returned %s:\n%s" % (cmd, st, op)

        target_last_commit = lastcommits[to_branch][0]
        linter_result=None
        if merge_type == 'single':
            print 'regular merge done. resetting to last %s commit %s'\
                  % (to_branch, target_last_commit)
            if self.got_untracked(repo):
                raise Exception('got untracked files in single merge.')
            cmd = 'git reset {target_last_commit}'.format(
                repo=repo, target_last_commit=target_last_commit)
            st, op = gso(repo, cmd)
            assert st == 0, op

            sm_updated = self.handle_submodules(repo, to_branch)

            print 'reset succesful.'
            if self.args.linters:
                print "Run linter for python source"
                linter_result = self.run_linters(repo)
            cmd = 'git add . && git add -u'.format(repo=repo)
            print 'running %s' % cmd
            st, op = gso(repo, cmd)
            assert st == 0
            print 'added all files and deletions for commit.'
            if not message:
                raise Exception('--message not specified in single merge.')
            if self.args.allowidentical:
                emptyallow='--allow-empty'
            else:
                emptyallow=''
            cmd = 'git commit {emptyallow} -m "{message}"'.format(
                repo=repo, message=message,emptyallow=emptyallow)
            st, op = gso(repo, cmd)
            assert st == 0,"commit failed with %s => %s\n%s"%(cmd,st,op)
            print 'succesfully re-merged.'

        elif merge_type == 'standard':
            print 'regular merge done. doing submodules'
            sm_updated = self.handle_submodules(repo, to_branch)
            if self.args.linters:
                print "Run linter for python source"
                linter_result = self.run_linters(repo,withbranch=self.args.from_branch)

        #check if there are any differences
        if not self.args.nocheckdiff and not self.args.is_reverse:
            cmd = 'git diff {from_branch} {to_branch}'.format(
                from_branch=from_branch, to_branch=to_branch)
            cmd += " | " + """ egrep -v '^(\+\+\+|\-\-\-|@@|(\-|\+)Subproject|diff|index)'"""
            st, op = gso(
                repo, cmd)
            assert st in [0, 256], "%s => %s" % (cmd, st)
            opl = len(op.split('\n'))
            if opl > 1:
                print op
                raise Exception('got a difference of %s lines between branches after merge.' % opl)


        pushcmd = 'git push origin {target_branch}'.format(
            repo=repo, target_branch=to_branch)
        if not self.args.push or self.args.nopush:
            torun = 'cd %s && ' % (
                os.path.join(c.REPODIR, repo)) + pushcmd + ' && cd ../..'
        if not conflicts and self.args.push:
            st, op = gso(repo, pushcmd)
            assert st == 0
            torun = None
        rt = {'torun': torun, 'sm_updated': sm_updated, 'conflicts': conflicts}
        if linter_result: rt['linters']=linter_result
        return rt
    aborted = []

    def merge(self, repo, from_branch, to_branch, message):
        print 'WORKING %s MERGE on %s %s => %s' % (self.args.merge_type.upper(), repo, from_branch, to_branch)
        assert repo in self.repos
        self.clone(repo,[from_branch,to_branch])

        lastcommits = {}
        for br in [from_branch, to_branch]:
            if br:
                if not self.checkout(repo, br):
                    self.aborted.append(
                        {'repo': repo, 
                         'source_branch': from_branch, 
                         'target_branch': to_branch, 
                         'reason': 'initial checkout of %s failed.' % br})
                    return
                #print('supposedly checkout out %s / %s'%(repo,br))
                lastcommits[br] = self.get_last_commits(repo, br, commits=c.REVS_TO_CHECK_BACK)
            else:
                lastcommits[br] = None

        self.checkout(repo, from_branch)
        if self.got_untracked(repo):
            raise Exception('has untracked files.')
        if to_branch:
            target_last_commit = lastcommits[to_branch][0]
        else:
            target_last_commit = None
        source_last_commit = lastcommits[from_branch][0]

        if self.args.merge_type == 'single':
            if target_last_commit not in lastcommits[from_branch]\
                    and not self.args.nolastcheck:
                print 'target branch ({target_branch}) last commit '\
                    '{target_last_commit} is not present '\
                    'in source branch {source_branch}'\
                    .format(target_branch=to_branch,
                            source_branch=from_branch,
                            target_last_commit=target_last_commit)
                self.checkout(repo, to_branch)
                last_commit_w_msg = self.get_last_commits(
                    repo, to_branch, 1, True)[0]
                if last_commit_w_msg['message'] == message:
                    self.aborted.append({
                        'repo': repo,
                        'source_branch': from_branch,
                        'target_branch': to_branch,
                        'reason': 'Already merged.'})
                    return
                print 'last commits on %s' % from_branch
                print lastcommits[from_branch]
                self.aborted.append({
                    'repo': repo,
                    'source_branch': from_branch,
                    'target_branch': to_branch,
                    'reason': 'Missing last target commit on source.'.upper(),
                    'reverse_cmd':'cd %(repodir)s && git checkout %(from_branch)s && git merge %(to_branch)s && git log -1 && git push origin %(from_branch)s && cd ../..'%{'repodir':'repos/%s'%repo,'from_branch':from_branch,'to_branch':to_branch}
                    })
                
                return
        try:
            if not self.args.is_reverse and target_last_commit == source_last_commit and not self.args.allowidentical:
                raise Exception(
                    'WARNING: branches %s and %s are identical.'
                    % (from_branch, to_branch))

            assert self.args.merge_type in ['single', 'standard', 'none']
            methname = '%s_merge' % self.args.merge_type
            meth = getattr(self, methname)
            print 'invoking %s' % methname
            rt = meth(self, repo, from_branch, to_branch, lastcommits, message)
            print 'done.'
            torun = rt['torun']
            sm_updated = rt['sm_updated']
            conflicts = rt['conflicts']
            if self.args.merge_type == 'none':
                rev = lastcommits[from_branch][0]
                prev_rev = None
            else:
                rev = self.get_last_commits(repo, to_branch, 1)[0]
                prev_rev = lastcommits[to_branch][0]
            apnd = {'repo': repo,
                 'source_branch': from_branch,
                 'target_branch': to_branch,
                 'torun': torun,
                 'prev_rev': prev_rev,
                 'new_rev': rev,
                 'submodules_updated': sm_updated,
                 'conflicts': conflicts}
            if 'linters' in rt: apnd['linters']=rt['linters']
            if 'conflicts' in apnd and apnd['conflicts']:
                self.screwed_up.append(apnd)
            else:
                self.completed.append(apnd)
                self.completed_lst.append(repo)
        except Exception, e:
            import traceback
            self.screwed_up.append(
                {'repo': repo,
                 'source_branch': from_branch,
                 'target_branch': to_branch,
                 'error': str(e),
                 'traceback': traceback.format_exc()})

    @staticmethod
    def _sortaborted(e1, e2):
        return cmp(e1['reason'], e2['reason'])

    def print_item(self, i):
        print json.dumps(i, sort_keys=True, indent=True)

    def print_results(self):
        if len(self.completed):
            print '########## COMPLETE: ##########'
            for res in self.completed:
                self.print_item(res)
        self.aborted.sort(self._sortaborted)
        if len(self.aborted):
            print '########## ABORTED: ##########'
            for abrt in self.aborted:
                self.print_item(abrt)
        if len(self.screwed_up):
            print '########## SCREWED UP: ##########'
            for scr in self.screwed_up:
                self.print_item(scr)

    def cmdrun(self):

        optparser = argparse.ArgumentParser(
            description='merge branches across multiple repos with a '
                        'single commit.',
            add_help=True)

        optparser.add_argument(
            '--from', action='store', dest='from_branch', help='source branch',
            required=False)

        optparser.add_argument(
            '--to', action='store', dest='to_branch', help='target branch',default=c.DEFAULT_TARGET_BRANCH,
            required=False)

        optparser.add_argument('--reverse',
                               action='store_true',
                               dest='is_reverse',
                               help='should source/destination branches be reversed and standard used instead of squash?')
        optparser.add_argument(
            '--type', action='store', dest='merge_type',
            help='type of merge. one of single,standard', default='single')

        optparser.add_argument(
            '--message', action='store', dest='message',
            help='commit message for the merge commit')

        optparser.add_argument(
            '--repo', action='append', dest='repos',
            help='specify specific repository(ies) to merge. repeatable.')

        optparser.add_argument(
            '--nofetch', action='store_true', dest='nofetch',
            help='do not run git fetch -a')

        optparser.add_argument(
            '--nopull', action='store_true', dest='nopull',
            help='do not pull latest branches, use the ones that exist '
                 'locally.')

        optparser.add_argument(
            '--noclone', action='store_true', dest='noclone',
            help='avoid cloning missing repositories.')

        optparser.add_argument(
            '--nopush', action='store_true', dest='nopush',
            help='do not push - the default.')

        optparser.add_argument(
            '--push', action='store_true', dest='push',
            help='push to origin after merge is done locally.')

        optparser.add_argument(
            '--allrepos', action='store_true', dest='allrepos',
            help='merge all repositories instead of specifying via --repo')

        optparser.add_argument(
            '--purge', action='store_true', dest='purge',
            help='purge all checked out repos.')

        optparser.add_argument(
            '--purge-cache', action='store_true', dest='purge_cache',
            help='purge all locally cached repos.')

        optparser.add_argument(
            '--nolastcheck', action='store_true', dest='nolastcheck',
            help='do not check for presence of last '
                 'commits on source branches (DANGEROUS).')

        optparser.add_argument(
            '--linters', action='store_true', dest='linters',
            help='Run linters on modified files.')

        optparser.add_argument(
            '--allowidentical', action='store_true', dest='allowidentical',
            help='Allow merge between identical branches.')

        optparser.add_argument(
            '--nocheckdiff', action='store_true', dest='nocheckdiff',
            help='do not verify the absence of diff between branches post-merge. useful for standard merges.')
        optparser.add_argument(
            '--nocatch', action='store_true', dest='nocatch', 
            help='do not catch exceptions. useful for debugging.')

        optparser.add_argument(
            'repos',action='append',nargs='*')
        args = optparser.parse_args()

        self.setargs(args)

        if not args.from_branch and not args.repos:
            raise Exception(
                '--from is required if source branch is not specified '
                'per-repository in --repo')
        if args.merge_type != 'none' and not args.to_branch:
            raise Exception(
                '--to is required if merge type is other than "none"')
        if args.merge_type=='squash': args.merge_type='single'
        if args.is_reverse and args.merge_type=='single':
            args.merge_type='standard'
        elif args.is_reverse and args.merge_type=='standard':
            args.merge_type='single'
        erepos=[]
        for r in args.repos:
            if type(r)==list:
                for l in r:
                    erepos.append(l)
            else:
                erepos.append(r)

        args.repos = erepos
        
        if args.allrepos:
            dorepos = [{'from_branch':args.from_branch, 
                        'repo':repo} for repo in c.REPOS]
        elif args.repos and len(args.repos):
            argrepos = {}
            for repo in args.repos:
                if '/' in repo:
                    repo, from_branch = repo.split('/')
                else:
                    repo = repo  # duh
                    assert args.from_branch, "--from not specified."
                    from_branch = args.from_branch
                argrepos[repo] = from_branch

            dorepos = [] ; doing=[]
            for repo in c.REPOS:
                if repo in argrepos:
                    dorepos.append(
                        {'from_branch': argrepos[repo], 
                                    'repo': repo})
                    doing.append(repo)
            dff = set(argrepos.keys())-set(doing)
            if len(dff):
                raise Exception('some repos unrecognized: %s'%dff)
        else:
            raise Exception('no repos or the --allrepos flag specified.')

        for repobj in dorepos:
            if args.is_reverse:
                inter = repobj['from_branch']
                repobj['from_branch'] = args.to_branch
                args.to_branch = inter
                print 'IS REVERSE: %s -> %s'%(repobj['from_branch'],args.to_branch)
            self.merge(
                repobj['repo'], repobj['from_branch'],
                args.to_branch, args.message)
        self.print_results()

if __name__ == '__main__':
    # init and run parser
    m = AutoMerger()
    m.cmdrun()
