[source] = System.argv()
Code.compiler_options(no_warn_undefined: :all)
for file <- ~w(domain directory eventing), do: Code.require_file(Path.join(source, file <> ".exs"))
ExUnit.start()

defmodule ProjectTransportRestoreTest do
  use ExUnit.Case
  alias ADHD.Eventing, as: E
  defp epoch, do: String.duplicate("e", 32)
  defp config, do: %{"project_epoch" => epoch(), "topic_generation" => epoch(),
    "eventing" => %{"enabled" => false, "topic_prefix" => "adhd", "rest_url" => "http://127.0.0.1:1"}}
  defp state(eventing), do: %{schema: 4, project_epoch: epoch(), server_id: "server", project: "red", eventing: eventing}

  test "only unfinished transport is requeued and original metadata stays offline" do
    frozen = %{"id" => "subscription-retained", "revision" => 9, "filter" => "original frozen filter"}
    rows = Map.new([{"done", :materialized, 7}, {"observed", :observed, 8}, {"pending", :pending, nil}], fn {id, status, offset} ->
      {id, %{state: status, offset: offset, broker_observed: true, retry_at: 999999,
        subscriptions: [frozen], event: %{"event_id" => id}, filter_done: 3}}
    end)
    original = %{E.empty() | events: rows, sequence: 43, next_offset: 9,
      binding: "old-binding", quarantine: %{"9" => %{"reason" => "INVALID_ENVELOPE"}},
      gap: %{"from_offset" => 8}, last_error: %{"code" => "QUARANTINED_EVENT"},
      filter_jobs: %{{"done", "subscription-retained", 9} => "job-retained"},
      filter_ready: MapSet.new(["job-retained"])}
    input = state(original)
    output = E.restore_state(input, config(), "restore")
    assert output.project_epoch == input.project_epoch
    assert output.eventing.next_offset == 0
    assert output.eventing.sequence == 43
    assert output.eventing.quarantine == %{}
    assert output.eventing.gap == nil
    assert output.eventing.events["done"].state == :materialized
    for id <- ["observed", "pending"] do
      assert output.eventing.events[id].state == :pending
      assert output.eventing.events[id].retry_at == 0
    end
    for {id, row} <- rows do
      restored = output.eventing.events[id]
      assert restored.offset == nil
      assert restored.broker_observed == false
      assert restored.event == row.event
      assert restored.subscriptions == row.subscriptions
      assert restored.filter_done == row.filter_done
    end
    assert output.eventing.filter_jobs == original.filter_jobs
    assert output.eventing.filter_ready == original.filter_ready
    assert [history] = output.eventing.restore_history
    assert history.quarantine == original.quarantine
    assert history.gap == original.gap
    assert history.binding == original.binding
    assert history.next_offset == original.next_offset
    assert history.offsets == %{"done" => 7, "observed" => 8, "pending" => nil}
    assert input.eventing == original
  end

  test "initialization has no invented history and disabled preflight requires no network service" do
    output = E.restore_state(state(E.empty()), config(), "initialize")
    assert output.eventing.restore_history == []
    assert output.eventing.events == %{}
    assert :ok == E.preflight_restore(config(), output)
  end

  test "legacy topic names survive and fresh topic epoch is required for restored state" do
    s = state(E.empty())
    legacy = Map.put(config(), "topic_generation", nil)
    expected = "adhd.b3eacd33433b31b5.b1f51a511f1da0cd"
    assert E.topic(legacy, s) == expected <> ".events.v1"
    assert E.topic(config(), s) == expected <> ".r" <> epoch() <> ".events.v1"
    assert catch_throw(E.restore_state(s, legacy, "restore")) == {:domain, "INVALID_PARAMS"}
  end
end
