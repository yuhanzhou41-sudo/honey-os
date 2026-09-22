import { requestJson } from "./client";
export type StudyPlanStatus="draft"|"active"|"paused"|"completed"|"archived";
export type StudyPlanSource="honeyos_generated"|"markdown_import"|"manual";
export type StudyTaskStatus="planned"|"in_progress"|"completed"|"skipped"|"deferred";
export type StudyTask={id:string;plan_id:string|null;title:string;description:string;scheduled_date:string;planned_minutes:number;status:StudyTaskStatus;order_index:number;review_required:boolean;created_at:string;updated_at:string};
export type StudyPlan={id:string;schema_version:1;title:string;description:string;start_date:string;end_date:string;status:StudyPlanStatus;focus_minutes:number;break_minutes:number;long_break_minutes:number;long_break_after_sessions:number;source_type:StudyPlanSource;goals:string[];tasks:StudyTask[];created_at:string;updated_at:string};
export type CreateStudyPlan={title:string;description?:string;start_date:string;end_date:string;focus_minutes?:number;break_minutes?:number;long_break_minutes?:number;long_break_after_sessions?:number;goals?:string[]};
export type CreateStudyTask={title:string;description?:string;scheduled_date:string;planned_minutes?:number;order_index?:number;review_required?:boolean};
export type UpdateStudyTask=Partial<CreateStudyTask>&{status?:StudyTaskStatus};
export const listStudyPlans=()=>requestJson<{plans:StudyPlan[]}>("/api/study/plans");
export const createStudyPlan=(p:CreateStudyPlan)=>requestJson<{plan:StudyPlan}>("/api/study/plans",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
export const updateStudyPlan=(id:string,p:Partial<CreateStudyPlan>&{status?:StudyPlanStatus})=>requestJson<{plan:StudyPlan}>(`/api/study/plans/${encodeURIComponent(id)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
export const deleteStudyPlan=(id:string)=>requestJson<{id:string;deleted:true}>(`/api/study/plans/${encodeURIComponent(id)}`,{method:"DELETE"});
export const createStudyTask=(pid:string,p:CreateStudyTask)=>requestJson<{plan:StudyPlan}>(`/api/study/plans/${encodeURIComponent(pid)}/tasks`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
export const updateStudyTask=(pid:string,tid:string,p:UpdateStudyTask)=>requestJson<{plan:StudyPlan}>(`/api/study/plans/${encodeURIComponent(pid)}/tasks/${encodeURIComponent(tid)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
export const setStudyTaskStatus=(pid:string,tid:string,status:StudyTaskStatus)=>requestJson<{plan:StudyPlan}>(`/api/study/plans/${encodeURIComponent(pid)}/tasks/${encodeURIComponent(tid)}/status`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});
export const deleteStudyTask=(pid:string,tid:string)=>requestJson<{plan:StudyPlan}>(`/api/study/plans/${encodeURIComponent(pid)}/tasks/${encodeURIComponent(tid)}`,{method:"DELETE"});

export type StudySessionStatus="planned"|"running"|"paused"|"completed"|"abandoned";
export type StudySessionType="focus"|"short_break"|"long_break"|"review"|"quiz"|"flashcard";
export type StudySession={id:string;task_id:string;session_type:StudySessionType;status:StudySessionStatus;started_at:string|null;expected_end_at:string|null;ended_at:string|null;planned_minutes:number;actual_minutes:number;user_summary:string;created_at:string;updated_at:string};
export const listStudySessions=(pid:string,tid:string)=>requestJson<{sessions:StudySession[]}>(`/api/study/plans/${encodeURIComponent(pid)}/tasks/${encodeURIComponent(tid)}/sessions`);
export const createStudySession=(pid:string,tid:string,p:{planned_minutes?:number;user_summary?:string;session_type?:StudySessionType}={})=>requestJson<{session:StudySession}>(`/api/study/plans/${encodeURIComponent(pid)}/tasks/${encodeURIComponent(tid)}/sessions`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
export const getStudySession=(sid:string)=>requestJson<{session:StudySession}>(`/api/study/sessions/${encodeURIComponent(sid)}`);
export const startStudySession=(sid:string)=>requestJson<{session:StudySession}>(`/api/study/sessions/${encodeURIComponent(sid)}/start`,{method:"POST"});
export const pauseStudySession=(sid:string)=>requestJson<{session:StudySession}>(`/api/study/sessions/${encodeURIComponent(sid)}/pause`,{method:"POST"});
export const resumeStudySession=(sid:string)=>requestJson<{session:StudySession}>(`/api/study/sessions/${encodeURIComponent(sid)}/resume`,{method:"POST"});
export const completeStudySession=(sid:string)=>requestJson<{session:StudySession}>(`/api/study/sessions/${encodeURIComponent(sid)}/complete`,{method:"POST"});
export const abandonStudySession=(sid:string)=>requestJson<{session:StudySession}>(`/api/study/sessions/${encodeURIComponent(sid)}/abandon`,{method:"POST"});

export type StudyPomodoroState={focuses_in_cycle:number;cycle_length:number;next_session_type:StudySessionType;next_minutes:number;current_session_id:string|null;current_session_type:StudySessionType|null;current_session_status:StudySessionStatus|null};
export const getStudyPomodoroState=(pid:string)=>requestJson<{pomodoro:StudyPomodoroState}>(`/api/study/plans/${encodeURIComponent(pid)}/pomodoro`);


// === Phase 4 Study Library ===
export type StudyResource={
  id:string;
  attachment_id:string;
  title:string;
  resource_type:string;
  course_or_subject:string;
  metadata:Record<string,unknown>;
  created_at:string;
  updated_at:string;
};

export type CreateStudyResource={
  attachment_id:string;
  title:string;
  resource_type:string;
  course_or_subject?:string;
  metadata?:Record<string,unknown>;
};

export type StudyResourceSearchHit={
  resource_id:string;
  attachment_id:string;
  title:string;
  resource_type:string;
  course_or_subject:string;
  metadata:Record<string,unknown>;
  snippet:string;
};

export type StudyResourceContent={
  extracted_text:string;
  extraction_kind:string;
  indexed_at:string;
};

function studyResourceQuery(params:Record<string,string|number|undefined>){
  const query=new URLSearchParams();
  for(const [key,value] of Object.entries(params)){
    if(value!==undefined && value!=="") query.set(key,String(value));
  }
  const suffix=query.toString();
  return suffix?`?${suffix}`:"";
}

export const listStudyResources=(filters:{course_or_subject?:string;resource_type?:string}={})=>
  requestJson<{resources:StudyResource[]}>(`/api/study/resources${studyResourceQuery(filters)}`);

export const createStudyResource=(payload:CreateStudyResource)=>
  requestJson<{resource:StudyResource}>("/api/study/resources",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload),
  });

export const getStudyResource=(id:string)=>
  requestJson<{resource:StudyResource}>(`/api/study/resources/${encodeURIComponent(id)}`);

export const deleteStudyResource=(id:string)=>
  requestJson<{id:string;deleted:true}>(`/api/study/resources/${encodeURIComponent(id)}`,{
    method:"DELETE",
  });

export const getStudyResourceContent=(id:string)=>
  requestJson<{content:StudyResourceContent}>(`/api/study/resources/${encodeURIComponent(id)}/content`);

export const searchStudyResources=(filters:{
  q?:string;
  course_or_subject?:string;
  resource_type?:string;
  limit?:number;
}={})=>
  requestJson<{results:StudyResourceSearchHit[]}>(`/api/study/resources/search${studyResourceQuery(filters)}`);
// === /Phase 4 Study Library ===
