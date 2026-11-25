"""Evaluate labeled transcripts and edit intervals without publishing any music.

Usage: python benchmarks/evaluate.py reference.json predicted.json
JSON: {"words":[{"text":"example","start":0,"end":1}],"edits":[{"start":0,"end":1}]}
"""
import json
import re
import sys
from pathlib import Path

def wer(reference,predicted):
    a=re.findall(r'\w+',reference.casefold());b=re.findall(r'\w+',predicted.casefold());row=list(range(len(b)+1))
    for i,left in enumerate(a,1):
        new=[i]
        for j,right in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(left!=right)))
        row=new
    return row[-1]/max(1,len(a))

def interval_metrics(reference,predicted,threshold=.3):
    used=set();hits=0
    for edit in predicted:
        for i,truth in enumerate(reference):
            if i in used:continue
            overlap=max(0,min(edit['end'],truth['end'])-max(edit['start'],truth['start']))
            union=max(edit['end'],truth['end'])-min(edit['start'],truth['start'])
            if union>0 and overlap/union>=threshold:used.add(i);hits+=1;break
    return {'precision':hits/max(1,len(predicted)),'recall':hits/max(1,len(reference)),
            'matched':hits,'missed':len(reference)-hits,'false_alarms':len(predicted)-hits}

if __name__=='__main__':
    reference,predicted=[json.loads(Path(p).read_text(encoding='utf-8')) for p in sys.argv[1:3]]
    result=interval_metrics(reference.get('edits',[]),predicted.get('edits',[]))
    result['word_error_rate']=wer(' '.join(w['text'] for w in reference.get('words',[])),' '.join(w['text'] for w in predicted.get('words',[])))
    print(json.dumps(result,indent=2))
