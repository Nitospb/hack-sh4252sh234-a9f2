import type { NextRequest } from "next/server";
const allowed=new Set(["health","companies","company","article","news","feed","insight","events","profile","saved","context","analysis","chat","runs","run","metrics","bank-sources","bank-file","review"]);
async function forward(request:NextRequest,context:{params:Promise<{path:string[]}>}){
 const {path}=await context.params;
 if(path.length!==1||!allowed.has(path[0]))return Response.json({error:"Not found"},{status:404});
 if(request.method==="POST"){
   const origin=request.headers.get("origin");
   if(origin){let parsed:URL;try{parsed=new URL(origin);}catch{return Response.json({error:"Invalid origin"},{status:403});}
     if(parsed.host.toLowerCase()!==request.headers.get("host")?.toLowerCase()||!["http:","https:"].includes(parsed.protocol))return Response.json({error:"Invalid origin"},{status:403});}
 }
 if(Number(request.headers.get("content-length")||0)>65536)return Response.json({error:"Request too large"},{status:413});
 const body=request.method==="POST"?await request.text():undefined;
 if(body&&new TextEncoder().encode(body).length>65536)return Response.json({error:"Request too large"},{status:413});
 try{
  const base=process.env.ALFA_API_URL||`http://127.0.0.1:${process.env.ALFA_API_PORT||"8091"}`;
  const response=await fetch(`${base}/${path[0]}${request.nextUrl.search}`,{method:request.method,headers:{"Content-Type":"application/json",...(process.env.ALFA_INTERNAL_TOKEN?{"X-Alfa-Internal":process.env.ALFA_INTERNAL_TOKEN}:{})},body,cache:"no-store",signal:AbortSignal.timeout(30000)});
  return new Response(response.body,{status:response.status,headers:{"Content-Type":response.headers.get("Content-Type")||"application/json; charset=utf-8","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}});
 }catch{return Response.json({error:"Сервис данных недоступен. Проверьте запуск API."},{status:503});}
}
export const GET=forward;export const POST=forward;
