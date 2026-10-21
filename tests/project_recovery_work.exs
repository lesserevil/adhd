[source] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for file <- ~w(domain projects project_backup storage_registry config directory resources records history_evaluator history retrieval selection retrieval_index retrieval_jobs archive_policy archive feedback_groups feedback replay optimization eventing store source_queries recovery_work),
  do: Code.require_file(Path.join(source,file<>".exs"))
ExUnit.start()

defmodule ProjectRecoveryWorkTest do
  use ExUnit.Case
  alias ADHD.RecoveryWork, as: W
  defp epoch,do: String.duplicate("a",32)
  defp config,do: %{"project_epoch"=>epoch(),"project_status"=>"active","matcher"=>nil}
  defp state do
    %{schema: 4,project_epoch: epoch(),history_queries: %{},retrieval_queries: %{},
      archive_queries: %{},replay_queries: %{},queries: %{},source_queries: %{},incoming: %{},source_incoming: %{}}
  end
  defp pending do
    %{"id"=>"retained-query","status"=>"pending","inflight"=>%{"timeout_ms"=>80},
      "usage"=>ADHD.History.usage_zero(),"frozen_policy"=>%{"model"=>"original-model","threshold_ppm"=>500000}}
  end
  test "disabled models retain accepted IDs and frozen policy while settling unknown completed calls" do
    q=pending()
    original=%{state()|history_queries: %{q["id"]=>q},retrieval_queries: %{q["id"]=>q}}
    restored=W.prepare(original,config(),"restore")
    for field<-[:history_queries,:retrieval_queries] do
      after_q=restored[field][q["id"]]
      assert after_q["id"]==q["id"]
      assert after_q["status"]=="pending"
      assert after_q["inflight"]==nil
      assert after_q["frozen_policy"]==q["frozen_policy"]
      assert after_q["usage"]["uncertain_calls"]==1
      assert after_q["usage"]["time_ms"]==80
    end
    assert length(hd(restored.recovery_work_audit)["work"])==2
    assert original.history_queries[q["id"]]["inflight"]!=nil
  end
  test "completed evidence is preserved and initialization invents no old work" do
    completed=%{"id"=>"completed-legacy","status"=>"completed","inflight"=>nil,"answer"=>%{"support_ids"=>["original-legacy"]}}
    original=%{state()|history_queries: %{completed["id"]=>completed}}
    restored=W.prepare(original,config(),"restore")
    assert restored.history_queries==original.history_queries
    assert W.prepare(state(),config(),"initialize")==state()
  end
  test "original remote deadlines expire without rewriting live pinned query identities" do
    expired=%{"id"=>"past-query","status"=>"pending","deadline_at"=>"2000-01-01T00:00:00Z"}
    live=%{"id"=>"future-query","status"=>"pending","deadline_at"=>"2099-01-01T00:00:00Z"}
    source=%{value: Map.put(expired,"results",[%{"status"=>"pending","owner_server_id"=>"pinned-owner"}]),peer_ids: ["pinned-peer"]}
    original=%{state()|queries: %{"past-query"=>expired,"future-query"=>live},source_queries: %{"past-source"=>source},
      incoming: %{"incoming"=>%{status: "pending",deadline: expired["deadline_at"],response: nil}},
      source_incoming: %{"incoming-source"=>%{status: "pending",command: %{"deadline_at"=>expired["deadline_at"]},response: nil}}}
    restored=W.prepare(original,config(),"restore")
    assert restored.queries["past-query"]["status"]=="partial"
    assert restored.queries["future-query"]==live
    assert restored.source_queries["past-source"].peer_ids==source.peer_ids
    assert restored.source_queries["past-source"].value["results"]==[%{"status"=>"unavailable","owner_server_id"=>"pinned-owner"}]
    assert restored.incoming["incoming"].status=="expired"
    assert restored.source_incoming["incoming-source"].status=="expired"
    actions=hd(restored.recovery_work_audit)["work"]
    assert Enum.any?(actions,&(&1["id"]=="future-query" and &1["action"]=="resume-pinned-idempotent"))
  end
end
