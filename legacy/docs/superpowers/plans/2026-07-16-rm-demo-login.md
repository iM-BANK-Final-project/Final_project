# RM Copilot Demo Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-only `test / 1234` login that shows the supplied brand image, plays the existing iM Bank splash after successful authentication, and then reveals the unchanged RM service.

**Architecture:** A focused `LoginPage` owns form presentation and delegates credential checking to `App`. `App` becomes a three-phase entry state machine (`login`, `splash`, `service`) and stores only an authenticated marker in `sessionStorage`; the existing page-selection state and API-backed service components remain unchanged.

**Tech Stack:** React 19, Vite 6, Vitest 4, Testing Library, CSS, browser `sessionStorage`

## Global Constraints

- This is local demo authentication, not a production security boundary.
- The only accepted credential pair is username `test` and password `1234`.
- Store no username or password in `sessionStorage`; store only an authenticated marker.
- The first successful login plays the existing 2.7-second splash; an authenticated reload opens the service directly.
- Preserve `TopNav`, the page order, existing service pages, API calls, and page-state navigation.
- Do not add a router, authentication dependency, FastAPI endpoint, user database, logout, signup, or account recovery.
- Copy the supplied image into the React project so runtime rendering does not depend on `/Users/gggyyu/Downloads`.

---

## File Structure

- Create `src/frontend/rm-insight-copilot/src/components/LoginPage.jsx`: login form UI and local form state.
- Create `src/frontend/rm-insight-copilot/src/components/LoginPage.test.jsx`: form submission, error rendering, and password visibility behavior.
- Create `src/frontend/rm-insight-copilot/src/App.test.jsx`: entry-state integration and session restoration behavior.
- Modify `src/frontend/rm-insight-copilot/src/App.jsx`: credential validation and `login → splash → service` transitions.
- Modify `src/frontend/rm-insight-copilot/src/styles.css`: responsive two-column login layout and form states.
- Create `src/frontend/rm-insight-copilot/src/assets/rm-copilot-login.png`: project-owned copy of the supplied brand image.

### Task 1: Login form component

**Files:**
- Create: `src/frontend/rm-insight-copilot/src/components/LoginPage.test.jsx`
- Create: `src/frontend/rm-insight-copilot/src/components/LoginPage.jsx`

**Interfaces:**
- Consumes: `onLogin(username: string, password: string): boolean` from `App`.
- Produces: `LoginPage({ onLogin })`, a form that shows an inline error when `onLogin` returns `false`.

- [ ] **Step 1: Write failing form behavior tests**

Create tests that render `<LoginPage onLogin={vi.fn(() => false)} />`, submit `wrong / value`, and assert the callback arguments and `role="alert"` text. Add a second test with `vi.fn(() => true)` and assert no alert remains after submitting `test / 1234`. Add a third test that clicks the `비밀번호 표시` button and checks that the labeled password input changes from `type="password"` to `type="text"`.

```jsx
fireEvent.change(screen.getByLabelText("아이디"), { target: { value: "wrong" } });
fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "value" } });
fireEvent.submit(screen.getByRole("form", { name: "RM Copilot 로그인" }));
expect(onLogin).toHaveBeenCalledWith("wrong", "value");
expect(screen.getByRole("alert")).toHaveTextContent(
  "아이디 또는 비밀번호가 일치하지 않습니다."
);
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd src/frontend/rm-insight-copilot
npm test -- src/components/LoginPage.test.jsx
```

Expected: FAIL because `LoginPage.jsx` does not exist.

- [ ] **Step 3: Implement the minimal form component**

Implement controlled `username`, `password`, `showPassword`, and `error` state. Submit through `<form aria-label="RM Copilot 로그인">`; call `onLogin(username, password)` and set the exact error copy only when it returns false. Use semantic labels and a `type="button"` visibility control with an `aria-label` that changes between `비밀번호 표시` and `비밀번호 숨기기`.

Use the project asset via:

```jsx
import loginImage from "../assets/rm-copilot-login.png";
```

Render the image with alt text `iM Bank RM Copilot` and wrap it in a left brand panel. Do not embed credentials or credential comparison in this component.

- [ ] **Step 4: Add the project-owned image asset**

Copy `/Users/gggyyu/Downloads/Gemini_Generated_Image_1s58u01s58u01s58.png` to:

```text
src/frontend/rm-insight-copilot/src/assets/rm-copilot-login.png
```

Confirm with `file` that the copied file is a 1024×1024 PNG.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run `npm test -- src/components/LoginPage.test.jsx` from the frontend directory.

Expected: all `LoginPage` tests PASS with no React warnings.

- [ ] **Step 6: Commit the component slice**

```bash
git add src/frontend/rm-insight-copilot/src/components/LoginPage.jsx \
  src/frontend/rm-insight-copilot/src/components/LoginPage.test.jsx \
  src/frontend/rm-insight-copilot/src/assets/rm-copilot-login.png
git commit -m "feat: add RM demo login form"
```

### Task 2: App entry state machine

**Files:**
- Create: `src/frontend/rm-insight-copilot/src/App.test.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/App.jsx`

**Interfaces:**
- Consumes: `LoginPage({ onLogin })` from Task 1 and existing `SplashScreen`.
- Produces: `DEMO_SESSION_KEY = "rm-copilot-demo-authenticated"`, accepted credentials `test / 1234`, and the `login → splash → service` flow.

- [ ] **Step 1: Write failing entry-flow tests**

Mock the API-backed page modules with simple labeled components so this test covers only app orchestration. Clear `sessionStorage` and use fake timers in setup/teardown.

Cover these cases:

```jsx
render(<App />);
expect(screen.getByRole("form", { name: "RM Copilot 로그인" })).toBeInTheDocument();

// Wrong credentials stay on login.
// test / 1234 replaces login with the existing splash.
// vi.advanceTimersByTime(2700) replaces splash with the mocked Overview.
// Pre-setting the session key renders Overview immediately without login or splash.
```

Assert that a successful login stores exactly the authenticated marker, not the username or password.

- [ ] **Step 2: Run the focused test and verify RED**

Run `npm test -- src/App.test.jsx`.

Expected: FAIL because current `App` starts with `SplashScreen` and has no login phase.

- [ ] **Step 3: Implement the minimal app phase logic**

In `App.jsx`, add constants for the session key and demo credentials. Initialize the phase from a safe `sessionStorage.getItem` helper:

```jsx
const [entryPhase, setEntryPhase] = useState(() =>
  hasAuthenticatedSession() ? "service" : "login"
);
```

Add `handleLogin(username, password)` that returns `false` for all pairs except `test / 1234`. On success, attempt to store `"true"`, set the phase to `"splash"`, and return `true`. Catch storage exceptions without blocking the current login.

Run the 2.7-second timer only while `entryPhase === "splash"`. Render `LoginPage` for `login`, `SplashScreen` for `splash`, and the unchanged existing shell for `service`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run `npm test -- src/App.test.jsx`.

Expected: all entry-flow tests PASS and fake timers are restored after each test.

- [ ] **Step 5: Run both new component suites**

Run:

```bash
npm test -- src/components/LoginPage.test.jsx src/App.test.jsx
```

Expected: both suites PASS.

- [ ] **Step 6: Commit the state-machine slice**

```bash
git add src/frontend/rm-insight-copilot/src/App.jsx \
  src/frontend/rm-insight-copilot/src/App.test.jsx
git commit -m "feat: gate RM service behind demo login"
```

### Task 3: Responsive login styling and regression verification

**Files:**
- Modify: `src/frontend/rm-insight-copilot/src/styles.css`

**Interfaces:**
- Consumes: class names rendered by `LoginPage`.
- Produces: desktop left-image/right-form layout and narrow-screen stacked layout without altering service-page selectors.

- [ ] **Step 1: Add a structural style assertion before CSS changes**

In `LoginPage.test.jsx`, assert that the page container, brand panel, and form panel use the agreed class names, and that the image has the accessible name `iM Bank RM Copilot`. This test documents the styling contract while the visual CSS is added.

```jsx
expect(screen.getByTestId("login-page")).toHaveClass("login-page");
expect(screen.getByRole("img", { name: "iM Bank RM Copilot" })).toBeInTheDocument();
```

- [ ] **Step 2: Run the focused test**

Run `npm test -- src/components/LoginPage.test.jsx`.

Expected: PASS if Task 1 already exposes the structural classes; otherwise FAIL on the missing class/test id, then add only those attributes before continuing.

- [ ] **Step 3: Add scoped responsive CSS**

Add `.login-page`, `.login-brand-panel`, `.login-brand-image`, `.login-form-panel`, `.login-card`, `.login-field`, `.login-password-wrap`, `.login-password-toggle`, `.login-submit`, and `.login-error` rules.

Use a two-column grid at desktop widths, `min-height: 100vh`, bounded form width, visible keyboard focus styles, and the existing teal/green brand palette. At `max-width: 760px`, switch to one column, constrain the image panel height, and keep the form within viewport padding. Do not edit existing `.app-shell`, navigation, card, table, or KPI selectors except where the current media-query placement requires appending the new scoped rules.

- [ ] **Step 4: Run the complete frontend test suite**

Run `npm test` from `src/frontend/rm-insight-copilot`.

Expected: all existing and new tests PASS.

- [ ] **Step 5: Run the production build**

Run `npm run build`.

Expected: Vite exits 0 and emits the production bundle with the PNG asset.

- [ ] **Step 6: Inspect the final diff for scope and secrets**

Run:

```bash
git diff --check
git status --short
rg -n "test|1234|sessionStorage" src/frontend/rm-insight-copilot/src/App.jsx \
  src/frontend/rm-insight-copilot/src/components/LoginPage.jsx
```

Confirm the demo credentials occur only in `App.jsx` credential validation and tests, passwords are never written to storage, and unrelated dirty files remain untouched.

- [ ] **Step 7: Commit the styling and verification slice**

```bash
git add src/frontend/rm-insight-copilot/src/styles.css \
  src/frontend/rm-insight-copilot/src/components/LoginPage.test.jsx
git commit -m "style: add responsive RM login layout"
```

