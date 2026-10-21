[source] = System.argv()
Code.require_file(Path.join(source, "domain.exs"))
Code.require_file(Path.join(source, "allocator.exs"))
ExUnit.start()

defmodule ProjectAllocatorTest do
  use ExUnit.Case
  alias ADHD.Allocator, as: A
  defp header(epoch \\ String.duplicate("a", 32)),
    do: %{schema: 4, allocation_epoch: epoch, allocation_counter: 0, seq: 97}

  test "all object families share a counter independent of ordering" do
    kinds = ~w(publication subscription delivery query job history retrieval archive replay proposal primitive evaluation selection context evidence feedback label cohort index audit)
    {ids, state} = Enum.map_reduce(kinds, header(), fn kind, s -> A.allocate(s, kind) end)
    assert length(Enum.uniq(ids)) == length(kinds)
    assert state.seq == 97
    assert state.allocation_counter == length(kinds)
    Enum.zip(kinds, ids) |> Enum.each(fn {kind, id} ->
      assert Regex.match?(~r/\A[a-z][a-z0-9]{0,15}_[0-9a-f]{32}_[1-9a-z][0-9a-z]*\z/, id)
      assert String.starts_with?(id, kind <> "_")
    end)
  end

  test "restored counter and sequence cannot recreate lost post-backup IDs" do
    old = header()
    {lost_id, _} = A.allocate(%{old | allocation_counter: 123}, "publication")
    restored = header(String.duplicate("b", 32))
    {new_id, next} = A.allocate(%{restored | allocation_counter: 123}, "publication")
    refute new_id == lost_id
    assert next.allocation_counter == 124
    assert next.seq == old.seq
    # The caller can abandon a speculative allocation without mutating its input.
    assert restored.allocation_counter == 0
  end

  test "counter continues through deterministic snapshot round trip" do
    {first, state} = A.allocate(%{header() | allocation_counter: 34}, "job")
    saved = :erlang.term_to_binary(state, [:deterministic])
    {second, next} = A.allocate(:erlang.binary_to_term(saved, [:safe]), "job")
    assert String.ends_with?(first, "_z")
    assert String.ends_with?(second, "_10")
    assert next.allocation_counter == 36
  end

  test "exhaustion fails before wrapping or modifying retained state" do
    maximum = 9_007_199_254_740_991
    {_, state} = A.allocate(%{header() | allocation_counter: maximum - 1}, "delivery")
    assert state.allocation_counter == maximum
    assert catch_throw(A.allocate(state, "delivery")) == {:domain, "RESOURCE_EXHAUSTED"}
    assert state.seq == 97
  end

  test "missing or malformed admission headers never get inferred fresh" do
    for invalid <- [%{}, %{header() | schema: 3}, Map.delete(header(), :allocation_epoch),
                    %{header() | allocation_epoch: String.duplicate("A", 32)},
                    %{header() | allocation_counter: -1}, %{header() | allocation_counter: 1.0},
                    %{header() | allocation_counter: 9_007_199_254_740_992}] do
      assert catch_throw(A.allocate(invalid, "job")) == {:domain, "RECOVERY_REQUIRED"}
    end
    for kind <- ["", "Publication", "has-dash", String.duplicate("x", 17), nil] do
      assert catch_throw(A.allocate(header(), kind)) == {:domain, "INVALID_PARAMS"}
    end
  end
end
