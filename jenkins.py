#!/usr/bin/env python
import urllib2
import json
from commands import getstatusoutput as gso
from automerge import AutoMerger
from config import JENKINS_TARGET_BRANCH,JENKINS_JOBS,JENKINS_LOGIN,JENKINS_PASSWD,JENKINS_URL,JENKINS_REPO_SUBMODULES
import sys
import re
class Struct:
    def __init__(self, **entries): 
        self.__dict__.update(entries)

def getlastbuild(url):
    passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
    passman.add_password(None, JENKINS_URL, JENKINS_LOGIN, JENKINS_PASSWD)
    authhandler = urllib2.HTTPDigestAuthHandler(passman)
    opener = urllib2.build_opener(authhandler)
    f = opener.open(url)
    return json.loads(f.read())
    

def determine_fastforward(url,repo_order):
    revs={}
    for act in getlastbuild(url)['actions']:
        if act and 'buildsByBranchName' in act:
            asgn = repo_order.pop(0)
            revs[asgn]=act['buildsByBranchName']['origin/staging']['revision']['SHA1']
            #print 'assigned %s'%asgn
    assert not len(repo_order)
    return revs

def getargs(target_branch,rev,push):
    return Struct(**{'merge_type':'standard',
                     'purge':True,
                     'purge_cache':False,
                     'noclone':False,
                     'nopull':False,
                     'from_branch':rev,
                     'to_branch':target_branch,
                     'is_reverse':False,
                     'linters':False,
                     'nocheckdiff':False,
                     'push':push,
                     'nopush':False,
                     'allowidentical':True})

def perform_fastforward(repo,rev,push=False):
    print 'FAST FORWARDING %s TO %s'%(repo,rev)
    am = AutoMerger()
    am.completed = []
    am.args = getargs(JENKINS_TARGET_BRANCH,rev,push)
    am.merge(repo,rev,JENKINS_TARGET_BRANCH,'_')
    assert len(am.completed)==1,"completed %s for %s"%(am.completed,repo)
    for sm,pth in JENKINS_REPO_SUBMODULES.get(repo,{}).items():
        st,op = gso('cd repos/%s && git submodule | grep %s'%(repo,pth)) ; assert st==0
        cid = re.compile('^\-([0-9a-f]+) ').search(op).group(1)
        print 'UPDATING SUBMODULE %s at %s with rev %s'%(sm,pth,cid)
        ams = AutoMerger()
        ams.completed = []
        ams.args = getargs(JENKINS_TARGET_BRANCH,cid,push)
        ams.merge(sm,cid,JENKINS_TARGET_BRANCH,'_')
        assert len(ams.completed)==1,"completed %s for %s"%(ams.completed,sm)
        if ams.completed[0]['prev_rev']==ams.completed[0]['new_rev']:
            print 'NO CHANGES DETECTED IN %s'%sm
        else:
            print '%s : SUBMODULE UPDATED COMPLETE'%sm

    if am.completed[0]['prev_rev']==am.completed[0]['new_rev']:
        print 'NO CHANGES DETECTED in %s'%repo
    else:
        print 'SUCCESFULLY UPDATED: %s'%repo


if __name__=='__main__':
    for jn,job in JENKINS_JOBS.items():
        if jn in sys.argv:
            print 'WALKING JOB %s'%jn
            revs = determine_fastforward(job['url'],job['repos'])
            print 'got the following revs to ff: %s'%revs
            for repo,rev in revs.items():
                perform_fastforward(repo,rev,push='push' in sys.argv[1:])
