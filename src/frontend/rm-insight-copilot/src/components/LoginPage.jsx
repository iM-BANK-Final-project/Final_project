import { useState } from "react";
import { Eye, EyeOff, LockKeyhole, UserRound } from "lucide-react";

import loginImage from "../assets/rm-copilot-login.png";

const LOGIN_ERROR = "아이디 또는 비밀번호가 일치하지 않습니다.";

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = (event) => {
    event.preventDefault();
    const accepted = onLogin(username, password);
    setError(accepted ? "" : LOGIN_ERROR);
  };

  return (
    <main className="login-page">
      <section className="login-brand-panel" aria-label="RM Copilot 브랜드">
        <img
          className="login-brand-image"
          src={loginImage}
          alt="iM Bank RM Copilot"
        />
      </section>

      <section className="login-form-panel">
        <form
          className="login-card"
          aria-label="RM Copilot 로그인"
          onSubmit={handleSubmit}
        >
          <div className="login-heading">
            <span className="login-eyebrow">CORPORATE BANKING</span>
            <h1>로그인</h1>
            <p>RM Insight Copilot에 오신 것을 환영합니다.</p>
          </div>

          <label className="login-field" htmlFor="login-username">
            <span>아이디</span>
            <span className="login-input-wrap">
              <UserRound size={20} aria-hidden="true" />
              <input
                id="login-username"
                name="username"
                type="text"
                autoComplete="username"
                placeholder="아이디를 입력하세요"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </span>
          </label>

          <label className="login-field" htmlFor="login-password">
            <span>비밀번호</span>
            <span className="login-input-wrap login-password-wrap">
              <LockKeyhole size={20} aria-hidden="true" />
              <input
                id="login-password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="비밀번호를 입력하세요"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                className="login-password-toggle"
                type="button"
                aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 표시"}
                onClick={() => setShowPassword((visible) => !visible)}
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </span>
          </label>

          {error ? (
            <p className="login-error" role="alert">
              {error}
            </p>
          ) : null}

          <button className="login-submit" type="submit">
            로그인
          </button>

          <p className="login-demo-note">로컬 시연용 데모 로그인</p>
        </form>
      </section>
    </main>
  );
}
