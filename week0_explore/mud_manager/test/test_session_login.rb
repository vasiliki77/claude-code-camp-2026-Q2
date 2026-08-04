require_relative "helper"

# The login dance's branches.
#
# CircleMUD/tbaMUD answers a password in more ways than the obvious two, and
# getting one wrong costs a full timeout and produces an error that names the
# wrong problem ("read_until ... after 10.0s" rather than "the character is
# already in the world").
class TestSessionLogin < Minitest::Test
  include DaemonTest

  def with_session(already_in_use: false)
    mud = MudManager::FakeMud.new(password: PASSWORD, already_in_use: already_in_use).start
    session = MudManager::Session.new(host: "127.0.0.1", port: mud.port, timeout: 5.0)
    session.open
    yield mud, session
  ensure
    session&.close
    mud&.stop
  end

  def test_fresh_login_walks_the_menu
    with_session do |mud, session|
      session.login(NAME, PASSWORD)

      assert session.open?
      # The blank line and the "1" that answer the main menu.
      assert_includes mud.commands, "1"
    end
  end

  def test_takeover_login_skips_the_menu
    # "You take over your own body, already in use!" — a linkdead character
    # being reclaimed. Routine after a daemon exits, since CircleMUD keeps the
    # body in-world for a while. This used to hang until the read timed out.
    with_session(already_in_use: true) do |mud, session|
      session.login(NAME, PASSWORD)

      assert session.open?
      refute_includes mud.commands, "1", "take-over path must not answer a menu that was never shown"
    end
  end

  def test_takeover_login_is_usable_afterwards
    with_session(already_in_use: true) do |mud, session|
      session.login(NAME, PASSWORD)
      session.drain
      session.send_command("look")

      assert_match(/You look/, session.read_until_prompt)
      assert_includes mud.commands, "look"
    end
  end

  def test_wrong_password_raises_login_error
    with_session do |_mud, session|
      assert_raises(MudManager::Session::LoginError) { session.login(NAME, "not-the-password") }
    end
  end

  def test_timeout_message_names_the_enforced_timeout
    # Callers almost always rely on the default, and interpolating the nil
    # argument printed "after s" — hiding the one number that distinguishes
    # "too slow" from "waiting for the wrong thing".
    with_session do |_mud, session|
      err = assert_raises(MudManager::Session::Timeout) do
        session.read_until(/this text never arrives/, timeout: 0.2)
      end
      assert_match(/after 0.2s/, err.message)

      err2 = assert_raises(MudManager::Session::Timeout) do
        session.read_until(/nor does this/)
      end
      assert_match(/after 5.0s/, err2.message)
      refute_match(/after s/, err2.message)
    end
  end
end
