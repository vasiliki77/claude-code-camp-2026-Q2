require "minitest/autorun"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "boukensha"

# Models — the lookup Boukensha.run uses to size a Context before any backend
# exists. It is folded from the backend tables rather than hand-written,
# because the hand-written version had already drifted: it claimed
# claude-sonnet-4-6 was 200k while the Anthropic backend said 1M.
class TestModelsTable < Minitest::Test
  BACKENDS = Boukensha::Models::BACKENDS

  def test_every_backend_model_is_in_the_table
    BACKENDS.each do |backend|
      backend::MODELS.each_key do |model|
        assert Boukensha::Models.known?(model),
               "#{backend} declares #{model} but Models does not know it"
      end
    end
  end

  def test_windows_agree_with_the_backend_that_declares_them
    BACKENDS.each do |backend|
      backend::MODELS.each do |model, spec|
        assert_equal spec[:context_window], Boukensha::Models.context_window(model),
                     "#{model}: Models disagrees with #{backend}"
      end
    end
  end

  def test_no_model_is_claimed_by_two_backends
    all = BACKENDS.flat_map { |backend| backend::MODELS.keys }

    assert_equal all.uniq, all, "the same model id is declared by two backends"
  end

  def test_an_unknown_model_falls_back_conservatively
    refute Boukensha::Models.known?("no-such-model")
    assert_equal Boukensha::Models::DEFAULT_CONTEXT_WINDOW,
                 Boukensha::Models.context_window("no-such-model")
  end

  # The configured model has to resolve to a real window, or the agent compacts
  # against the 32k fallback while a 200k window sits unused.
  def test_the_configured_player_model_is_known
    settings = Boukensha.config.tasks(:player)
    skip "no player task configured" unless settings

    model = Boukensha::Tasks::Player.model(settings)

    assert Boukensha::Models.known?(model),
           "settings.yaml runs #{model}, which no backend declares"
  end
end
