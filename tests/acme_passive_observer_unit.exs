Code.require_file(Path.join(__DIR__, "acme_passive_observer.exs"))
ExUnit.start()
defmodule PassiveChecks do
  use ExUnit.Case
  test "whitelist strips argument lists, locations, state and return values" do
    value = ACMEPassiveObserver.sanitize(current_function: {File, :read, 1},
      current_stacktrace: [{File,:read,1,[file: ~c"private-key-path",line: 2]}, {File,:write,["secret-key"]}],
      status: :waiting, message_queue_len: 3, reductions: 4, dictionary: [secret: "key"], messages: ["private"])
    assert value == %{"function"=>["Elixir.File","read",1],"stack"=>[["Elixir.File","read",1]],
      "status"=>"waiting","queue"=>3,"reductions"=>4}
    refute JSON.encode!(value) =~ "secret"
    refute JSON.encode!(value) =~ "private"
    assert ACMEPassiveObserver.mfa({File,:write,["key"]}) == nil
  end
end
