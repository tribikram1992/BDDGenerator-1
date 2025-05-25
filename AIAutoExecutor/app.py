import streamlit as st
import json
import os
from ai_executor import AIUIExecutor

st.set_page_config(page_title="AI UI Real-Time Operation Creator", layout="wide")
st.title("AI UI Operation Creator (Real-time)")

# --- Load AI config if exists ---
ai_config = {
    "model": "",
    "api_key": "",
    "api_base": ""
}
config_path = "ai_config_sonnet.json"
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        try:
            loaded = json.load(f)
            ai_config.update(loaded)
        except Exception as e:
            st.warning(f"Could not read ai_config_sonnet.json: {e}")

with st.sidebar:
    st.header("AI Model Settings")
    model = st.text_input("Model Name", ai_config.get("model", "anthropic.claude-3-sonnet-20240229-v1:0"))
    api_key = st.text_input("API Key", ai_config.get("api_key", ""), type="password")
    api_base = st.text_input("API Base URL", ai_config.get("api_base", "https://your-bedrock-endpoint"))
    screenshot_dir = st.text_input("Screenshot Directory", "screenshots")
    report_path = st.text_input("Extent Report Path", "extent_report.html")
    st.markdown("""
        <small>
        Your API key and base URL are used only in your browser session and never sent anywhere else.
        </small>
        """, unsafe_allow_html=True)

st.markdown("""
### 📝 **Prompt Syntax Suggestions for Best Results**
- Prefer **step-by-step JSON** or clear, sequential natural language.
- Example JSON:
```json
[
  {"eventType": "navigate", "locatorType": "url", "locator": "https://example.com"},
  {"eventType": "input", "locatorType": "label", "locator": "Username", "value": "myuser"},
  {"eventType": "input", "locatorType": "label", "locator": "Password", "value": "secret"},
  {"eventType": "click", "locatorType": "button_text", "locator": "Sign In"},
  {"eventType": "wait_js", "value": "return typeof window.myAppReady !== 'undefined' && window.myAppReady===true;"}
]
```
- Or natural language:
    - Go to https://example.com
    - Enter "myuser" in the Username field
    - Enter "secret" in the Password field
    - Click the "Sign In" button
    - Wait until the dashboard is fully loaded

**Tips:**
- Use labels and visible text for fields and buttons.
- Mention if a step requires waiting for a UI or JS state.
- Specify frame or window if needed.
""")

if not api_key or not model or not api_base:
    st.warning("Please configure your AI API Key, Model, and Base URL in the sidebar, or set them in ai_config_sonnet.json.")
    st.stop()

ai_executor = AIUIExecutor(model, api_key, api_base, screenshot_dir=screenshot_dir, report_path=report_path)

prompt = st.text_area("Describe your UI operation(s) to run on your browser:", "Go to https://example.com, enter \"myuser\" in the Username field, and click the Sign In button.")

if 'object_repository' not in st.session_state:
    st.session_state['object_repository'] = {}
if 'actions' not in st.session_state:
    st.session_state['actions'] = []
if 'test_data' not in st.session_state:
    st.session_state['test_data'] = {}

def natural_language_for_step(step):
    et = step.get("eventType", "").lower()
    lt = step.get("locatorType", "")
    loc = step.get("locator", "")
    val = step.get("value", "")
    if et == "navigate":
        return f"Go to {loc}"
    if et == "input":
        return f'Enter "{val}" in the {lt}: {loc} field'
    if et == "click":
        return f'Click on the {lt}: {loc} element'
    if et == "press_enter":
        return f'Press ENTER on the {lt}: {loc} element'
    if et == "wait":
        return f'Wait for {val} seconds'
    if et == "wait_js":
        return f'Wait for JS condition: {val} to become true'
    return f"{et} on {lt}: {loc} with {val}"

def add_to_object_repository(step):
    key = f"{step.get('locatorType')}:{step.get('locator')}"
    st.session_state['object_repository'][key] = {
        "locatorType": step.get("locatorType"),
        "locator": step.get("locator"),
        "framePath": step.get("framePath", []),
        "window": step.get("window", None)
    }

def add_to_actions(step, nl):
    st.session_state['actions'].append({
        "natural_language": nl,
        "step": {k: v for k, v in step.items() if k in ["eventType", "locatorType", "locator", "value", "framePath", "window"]}
    })

def add_to_test_data(step):
    if step.get("eventType") == "input":
        key = f"{step.get('locatorType')}:{step.get('locator')}"
        st.session_state['test_data'][key] = step.get("value")

def clean_dict_for_json(obj):
    if isinstance(obj, dict):
        return {k: clean_dict_for_json(v) for k, v in obj.items() if is_json_serializable(v)}
    elif isinstance(obj, list):
        return [clean_dict_for_json(x) for x in obj if is_json_serializable(x)]
    return obj

def is_json_serializable(v):
    try:
        json.dumps(v)
        return True
    except:
        return False

if st.button("Execute UI Operation"):
    with st.spinner("Asking AI to plan steps..."):
        steps = ai_executor.ai_parse_steps(prompt)
    if not steps:
        st.error("AI could not generate a plan. Try rephrasing.")
    else:
        st.success("Plan generated! Executing...")
        logs = []
        result = ai_executor.run_steps(steps, log_callback=lambda m: logs.append(m))
        st.write("### Step-by-Step Review")
        for i, step in enumerate(steps):
            nl = natural_language_for_step(step)
            st.write(f"**Step {i+1}:** {nl}")
            passed = any("PASS" in log.get('status', '') for log in ai_executor.extent_logs if f"Step {i+1}:" in log.get('message', ''))
            if passed:
                if st.checkbox(f"Mark Step {i+1} as Validated?", key=f"v_{i}"):
                    add_to_object_repository(step)
                    add_to_actions(step, nl)
                    add_to_test_data(step)
            else:
                st.warning(f"Step {i+1} failed or could not be validated.")

        st.write("### Execution Logs")
        st.text("\n".join(logs))
        st.markdown(f"**Extent Report:** [{report_path}]({report_path})")

        st.write("### Download Artifacts")
        col1, col2, col3 = st.columns(3)
        with col1:
            try:
                obj_repo_json = json.dumps(clean_dict_for_json(st.session_state['object_repository']), indent=2)
                st.download_button("Download Object Repository", obj_repo_json, file_name="object_repository.json")
            except Exception as e:
                st.error(f"Object repo error: {e}")
        with col2:
            try:
                actions_json = json.dumps(clean_dict_for_json(st.session_state['actions']), indent=2)
                st.download_button("Download Actions", actions_json, file_name="actions.json")
            except Exception as e:
                st.error(f"Actions error: {e}")
        with col3:
            try:
                test_data_json = json.dumps(clean_dict_for_json(st.session_state['test_data']), indent=2)
                st.download_button("Download Test Data", test_data_json, file_name="test_data.json")
            except Exception as e:
                st.error(f"Test data error: {e}")
