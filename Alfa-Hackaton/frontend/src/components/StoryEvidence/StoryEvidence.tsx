import {EvidenceComparison} from "@/src/components/EvidenceComparison/EvidenceComparison";
import { displayDate, type Story } from "@/src/screens/Feed/recommendation-api";
import s from "./StoryEvidence.module.css";
function link(url:string){return /^https?:\/\//.test(url)?url:undefined;}
export function StoryEvidence({story,showFacts=true}:{story?:Story|null;showFacts?:boolean}){
 if(!story||story.member_count<2)return null;
 return <section className={s.panel} aria-label="Публикации об одном событии"><h3>Связанные публикации</h3>
 <p>{story.visible_evidence_count} доступных материалов · {story.distinct_hosts} доменов. Группа сформирована автоматически; общий первоисточник требует проверки.</p>
 <ul>{story.items.map(item=><li key={item.article_id}><a href={link(item.url)} target="_blank" rel="noreferrer">{item.title} ↗</a><small>{item.source} · {displayDate(item.published_at,true)}</small></li>)}</ul>
 {showFacts&&story.fact_comparison&&<EvidenceComparison report={story.fact_comparison} sources={story.items.map(x=>({id:x.article_id,title:x.source||x.title,url:x.url,published_at:x.published_at}))}/>}
 {!story.fact_comparison&&story.numeric_variants.length>0&&<details><summary>Числа для сопоставления</summary><p>Значения могут относиться к разным показателям или периодам. Это список для проверки, а не установленное противоречие.</p>{story.numeric_variants.map((row,i)=><div key={i}><strong>Единицы: {row.unit}</strong>{row.values.map(v=><div key={v.value}><p>{v.value}</p>{v.evidence.map((e,n)=><blockquote key={n}>{e.quote}<small>{story.items.find(x=>x.article_id===e.article_id)?.source||e.article_id}</small></blockquote>)}</div>)}</div>)}</details>}
 </section>;
}
