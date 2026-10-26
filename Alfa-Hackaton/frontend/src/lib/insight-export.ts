type Claim={text:string;conditional:boolean;source_ids:string[]};
type Exportable={insight:{title:string;status:string;event:{text:string};ai_application:Claim[];why_for_company:Claim[];risks:Claim[];opportunities:Claim[];actions:Claim[];missing_context:string[];limitations:string[];bank_view:null|{label:string;summary:string;applicability:string;limitations:string;source_ids:string[]}};news:{title:string;url:string;published_at:string};sources:{id:string;document_title:string;url:string;published_at:string;page:number}[];related_news?:{id:string;title:string;url:string;published_at:string}[]};
function absolute(url:string,origin:string){try{const parsed=new URL(url,origin);return ["https:","http:"].includes(parsed.protocol)?parsed.href:"";}catch{return "";}}
export function insightText(result:Exportable,origin:string,company=""){
 const i=result.insight;const lines=[i.title,...(company?[`Компания: ${company}`]:[]),"",i.event.text];
 const used=new Set<string>();
 const sections:[string,Claim[]][]=[["Оценка влияния",i.ai_application],["Почему это важно",i.why_for_company],["Риски",i.risks],["Возможности",i.opportunities],["Рекомендуемые действия",i.actions]];
 for(const [title,claims]of sections){if(!claims.length)continue;lines.push("",title);for(const c of claims){lines.push(`• ${c.conditional?"При указанных допущениях: ":""}${c.text}`);c.source_ids.forEach(id=>used.add(id));}}
 if(i.bank_view){const b=i.bank_view;lines.push("",b.label,b.summary,b.applicability,b.limitations);b.source_ids.forEach(id=>used.add(id));}
 if(i.missing_context.length)lines.push("","Уточнения",...i.missing_context.map(q=>`• ${q}`));
 if(i.limitations.length)lines.push("","Ограничения",...i.limitations.map(q=>`• ${q}`));
 const links=[{title:result.news.title,url:result.news.url,date:result.news.published_at},...result.sources.filter(p=>used.has(p.id)).map(p=>({title:`${p.document_title}, с. ${p.page}`,url:p.url,date:p.published_at})),...(result.related_news||[]).filter(p=>used.has(p.id)).map(p=>({title:p.title,url:p.url,date:p.published_at}))];
 lines.push("","Первоисточники");const seen=new Set<string>();
 for(const source of links){const url=absolute(source.url,origin);if(!url||seen.has(url))continue;seen.add(url);lines.push(`• ${source.title}${source.date?` (${source.date.slice(0,10)})`:""}\n${url}`);}
 lines.push("","Сценарная оценка сервиса; позиция банка отмечена отдельно.");
 return lines.join("\n");
}
