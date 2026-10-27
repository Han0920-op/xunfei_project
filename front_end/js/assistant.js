/* Guided intake remains a demo. Non-DEMO registration numbers call the backend
 * reviewed-snapshot checker; no diagnosis or OCR claims. */
(() => {
  "use strict";
  const S = window.FarmerStore;
  const questions = {
    distribution: {
      text: "异常是零星出现，还是一大片都有？",
      choices: ["只有几株", "局部一片", "很多地方都有", "还没看清"],
    },
    stage: {
      text: "小麦现在大约长到哪一步了？不知道也没关系。",
      choices: ["苗期", "返青或拔节", "抽穗或扬花", "灌浆或成熟", "不清楚"],
    },
    number: {
      text: "请找到包装上的“农药登记证号”，把号码发给我。",
      hint: "也可以先拍清楚包装标签，目前需要你手动确认号码。只将登记号、作物和防治对象发送到核对服务。",
    },
    target: {
      text: "你准备用它防治什么？还没弄清原因也可以如实说。",
      choices: ["赤霉病", "白粉病", "条锈病", "蚜虫", "还没确定"],
    },
    followup: {
      text: "和上次相比，现在看起来怎么样？",
      choices: ["看起来改善了", "没有明显变化", "更严重了", "说不清楚"],
    },
  };
  function message(type, values = {}) {
    return { id: S.id(), role: "assistant", type, ...values };
  }
  function create(kind = "disease") {
    return {
      id: S.id(),
      kind,
      title: kind === "medicine" ? "核对手里的药" : "这次小麦的问题",
      step: kind === "medicine" ? "number" : "start",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      archived: false,
      demo: true,
      facts: {},
      photos: [],
      messages: [],
      actions: [],
      followups: [],
      followupDate: "",
    };
  }
  function question(step) {
    return message("question", { step, ...questions[step] });
  }
  function startMedicine(previous) {
    const t = previous ? structuredClone(previous) : create("medicine");
    t.kind = "medicine";
    t.step = "number";
    t.messages.push(question("number"));
    t.updatedAt = new Date().toISOString();
    return t;
  }
  function startFollowup(previous) {
    const t = structuredClone(previous);
    t.archived = false;
    t.step = "followup";
    t.messages.push(question("followup"));
    t.updatedAt = new Date().toISOString();
    return t;
  }
  function intent(text) {
    return /登记证|核对.*药|这药.*能|药.*适用|^DEMO-|^[A-Za-z]{1,4}\d{5,}$/i.test(
      text,
    )
      ? "medicine"
      : "disease";
  }
  function diseaseResult(t) {
    const unknown =
      t.facts.stage === "不清楚" || t.facts.distribution === "还没看清";
    const description = t.facts.description || "";
    return message("result", {
      investigation: true,
      heading: unknown
        ? "还需要补一点现场信息"
        : "先补拍近景和全株，帮助分清原因",
      summary: "仅凭当前描述，不能确定病因，也不能判断是否需要打药。",
      now: /虫/.test(description)
        ? "拍清虫体和它聚集的部位，保留一张全株照片。"
        : "补拍异常部位近景和全株照片，记下是否还在扩大。",
      medicine: "原因还没确认，先不要依据这条示例回复选择农药。",
      explanation:
        "这是前端示例回复，没有识别你的照片或检索农技资料。实际判断需结合照片、生育期、发生程度和可追溯依据。",
      actions: ["photo", "medicine", "action", "schedule", "summary"],
    });
  }
  function knowledgeResult(t) {
    const k = t.facts.knowledge;
    const answer = t.facts.observationAnswer || "未补充";
    return message("result", {
      heading:
        answer === "没看到"
          ? "这个特征没看到，先不要按相似病名判断"
          : "现场细节记下了，先留好检查依据",
      summary: `你补充：${answer}。仅凭当前描述不能确定病因，也不能判断是否需要打药。`,
      now: "补拍异常部位近景和全株；若异常扩大，带上照片及实际处理记录请农技人员复核。",
      medicine: "知识文档的相似描述不等于用药依据。手里有药可另行核对登记号。",
      explanation: k.notice,
      knowledge: k,
      sourceLabel: "知识库观察参考 · 待农技审校 · 未识别图片",
      actions: ["photo", "medicine", "action", "schedule", "summary"],
    });
  }
  function registrationResult(t) {
    const number = t.facts.registration || "",
      target = t.facts.target || "";
    let heading = "登记信息还没核实，暂不能判断是否适用",
      summary =
        "当前未连接真实登记查询。请核对有效标签，必要时请农技人员协助。",
      tone = "caution",
      checks = [];
    if (/^DEMO-/i.test(number)) {
      const examples = {
        "DEMO-WHEAT-001": { crop: "小麦", target: "白粉病" },
        "DEMO-APHID-001": { crop: "小麦", target: "蚜虫" },
        "DEMO-MISMATCH-001": { crop: "水稻", target: "稻飞虱" },
        "DEMO-INCOMPLETE-001": { crop: "小麦", target: null },
      };
      const r = examples[number.toUpperCase()];
      if (!r) {
        summary = "没有找到这个演示编号。这不代表真实登记号不存在。";
      } else if (!r.target) {
        heading = "这个示例还缺少关键信息";
        summary = "防治对象和登记状态不完整，不能据此判断适用。";
        checks = [
          ["作物", r.crop],
          ["防治对象", "未提供"],
        ];
      } else if (
        r.crop !== "小麦" ||
        (target !== "还没确定" && r.target !== target)
      ) {
        heading = "这个示例与当前情况不匹配";
        summary = "示例登记的作物或防治对象不相符，不能把它用于当前情况。";
        tone = "danger";
        checks = [
          ["示例作物", r.crop],
          ["示例防治对象", r.target],
          ["你准备防治", target],
        ];
      } else {
        heading =
          target === "还没确定"
            ? "先确认防治对象，再判断是否适用"
            : "示例字段相符，还需要核对有效标签";
        summary = "这是虚构登记记录，未核验真实状态，不是实际产品或用药建议。";
        checks = [
          ["示例作物", r.crop],
          ["示例防治对象", r.target],
          ["真实有效状态", "未核实"],
        ];
      }
    }
    return message("check", {
      heading,
      summary,
      tone,
      number,
      checks,
      explanation:
        "只核对登记号还不够，还要确认作物、防治对象、剂型含量、标签版本和有效状态。当前不提供具体用量、混配比例或安全间隔期。",
      actions: ["label", "action", "schedule", "summary"],
    });
  }
  function plan(previous, input) {
    const t = previous ? structuredClone(previous) : create(intent(input.text));
    const text = String(input.text || "").trim();
    if (input.photo) t.photos.push(input.photo);
    t.messages.push({
      id: S.id(),
      role: "user",
      text:
        text ||
        (input.photo
          ? t.step === "number"
            ? "这张是药品包装标签"
            : "帮我看看这张照片"
          : ""),
      photoId: input.photo?.id,
    });
    t.updatedAt = new Date().toISOString();
    t.archived = false;
    const cropInjury =
      /(?:麦苗|小麦|麦子|叶片|植株|苗).{0,16}(?:中毒|药害)/.test(text);
    const personalExposure =
      /误服|人员暴露|喝了农药|误食农药|(?:我|人|孩子|家人|工人).{0,10}中毒/.test(
        text,
      );
    if (personalExposure || (/中毒/.test(text) && !cropInjury)) {
      t.step = "result";
      t.messages.push(
        message("result", {
          heading: "人员安全优先，请立即寻求专业帮助",
          summary:
            "这类情况需要当地急救或专业中毒咨询服务，请提供产品标签和暴露情况。",
          now: "停止在这里进行农业诊断，及时联系专业应急服务。",
          explanation: "智麦不提供人员中毒诊断、解毒或应急用药指导。",
          actions: ["summary"],
        }),
      );
      return t;
    }
    if (
      /^(玉米|水稻|番茄|棉花|油菜)|(?:这是|种的是|作物是)(?:玉米|水稻|番茄|棉花|油菜)|不是小麦/.test(
        text,
      )
    ) {
      t.step = "result";
      t.messages.push(
        message("result", {
          heading: "这次先请对应作物的农技人员帮看",
          summary:
            "智麦当前面向冬小麦，不把其他作物的问题套进小麦的判断和用药信息。",
          now: "保留现场照片和实际处理记录，交给对应作物的农技人员复核。",
          actions: ["summary"],
        }),
      );
      return t;
    }
    if (t.step === "followup") {
      if (input.photo) t.pendingFollowupPhotoId = input.photo.id;
      if (!input.choice) {
        t.followupNote = text;
        t.messages.push(question("followup"));
        return t;
      }
      t.followups.push({
        id: S.id(),
        date: S.date(),
        outcome: text,
        note: t.followupNote || "",
        photoId: t.pendingFollowupPhotoId || null,
      });
      t.followupDate = "";
      t.step = "result";
      t.messages.push(
        message("followup-result", {
          heading:
            text === "更严重了"
              ? "建议尽快请农技人员现场复核"
              : "这次变化记下了，我们接着跟踪",
          summary: `你反馈：${text}。这是现场观察，尚不能据此确认病因或药效。`,
          now:
            text === "更严重了"
              ? "带上前后照片和实际处理记录，请农技人员核对。"
              : "保留相近位置的照片，继续留意异常是否扩大。",
          beforeId: t.pendingFollowupPhotoId
            ? t.photos.filter((p) => p.id !== t.pendingFollowupPhotoId).at(-1)
                ?.id
            : null,
          afterId: t.pendingFollowupPhotoId || null,
          actions: ["photo", "action", "schedule", "summary"],
        }),
      );
      delete t.pendingFollowupPhotoId;
      return t;
    }
    if (t.kind === "medicine" && t.step === "number") {
      if (
        !text ||
        (input.photo && !/DEMO-|登记|[A-Za-z]{1,4}\d{5,}/i.test(text))
      ) {
        t.messages.push(
          message("question", {
            step: "number",
            text: "标签照片已收下。当前不能识别登记号，请看包装后手动输入。",
            hint: "这里不会把照片当作已经核验的登记信息。",
          }),
        );
        return t;
      }
      t.facts.registration = text
        .replace(/^.*?登记(?:证)?号[：:\s]*/, "")
        .trim()
        .toUpperCase();
      if (
        !/^DEMO-/i.test(t.facts.registration) &&
        !/^(?:PD|EX|LS)\d{6,12}$/.test(t.facts.registration)
      ) {
        t.messages.push(
          message("question", {
            step: "number",
            text: "这个号码格式还不完整，请只输入包装上的农药登记证号。",
            hint: "目前支持 PD、EX 或 LS 开头的完整编号。不要填写生产许可证号或商品条码。",
          }),
        );
        return t;
      }
      t.step = "target";
      t.messages.push(question("target"));
      return t;
    }
    if (t.kind === "medicine" && t.step === "target") {
      t.facts.target = text;
      t.step = "result";
      t.title = `核对农药 · ${t.facts.registration}`;
      t.messages.push(registrationResult(t));
      return t;
    }
    if (t.step === "start") {
      t.facts.description = text || "上传了现场照片";
      t.title = (text || "照片中的小麦异常").slice(0, 36);
      t.step = "distribution";
      t.messages.push(question("distribution"));
      return t;
    }
    if (t.step === "distribution") {
      t.facts.distribution = text;
      t.step = "stage";
      t.messages.push(question("stage"));
      return t;
    }
    if (t.step === "stage") {
      t.facts.stage = text;
      t.step = "result";
      t.messages.push(diseaseResult(t));
      return t;
    }
    if (t.step === "knowledge_followup") {
      t.facts.observationAnswer = text || "补充了照片，文字尚未确认";
      t.step = "result";
      t.messages.push(knowledgeResult(t));
      return t;
    }
    if (t.step === "result") {
      if (input.photo) {
        t.facts.additionalPhoto = input.photo.id;
        t.messages.push(
          message("note", {
            text: "补充照片已保存。当前演示尚未分析这张图，不据此更新病因或判断药效。",
            actions: ["followup", "summary"],
          }),
        );
      } else if (intent(text) === "medicine") {
        t.kind = "medicine";
        t.step = "number";
        t.messages.push(question("number"));
      } else {
        t.facts.additionalNote = text;
        t.messages.push(diseaseResult(t));
      }
      return t;
    }
    return t;
  }
  const respond = async (t, input, signal) => {
    const next = await new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", abort);
        try {
          resolve(plan(t, input));
        } catch (e) {
          reject(e);
        }
      }, 220);
      signal?.addEventListener("abort", abort, { once: true });
    });
    const last = next.messages.at(-1);
    if (last?.investigation) {
      const k = await window.KnowledgeClient.assist(next.facts, signal);
      next.facts.knowledge = k;
      if (
        k.status === "found" &&
        k.results.length &&
        typeof k.next_question === "string" &&
        Array.isArray(k.choices)
      ) {
        next.step = "knowledge_followup";
        next.messages[next.messages.length - 1] = message("question", {
          step: "knowledge_followup",
          text: k.next_question,
          hint: "参考你上传的知识文档补问，尚未识别图片或确认病因。看不清也可以直接说。",
          choices: k.choices,
          knowledge: k,
        });
      } else {
        next.messages[next.messages.length - 1] = {
          ...last,
          knowledge: k,
          sourceLabel:
            k.status === "no_match"
              ? "未检索到足够相关的资料 · 未识别图片"
              : "知识检索未完成 · 未识别图片",
          explanation: k.notice,
        };
      }
    }
    if (last?.type === "check" && !/^DEMO-/i.test(next.facts.registration)) {
      const r = await window.PesticideClient.check(
        next.facts.registration,
        next.facts.target,
        signal,
      );
      next.messages[next.messages.length - 1] = message("check", {
        ...last,
        heading: r.heading,
        summary: r.summary,
        tone: r.status === "mismatch" ? "danger" : "caution",
        checks: r.checks,
        explanation: r.explanation,
        verification: r,
        now: r.next_steps?.join(" "),
        sourceLabel:
          r.mode === "official_announcement_snapshot"
            ? "官方公告登记资料 · 当前有效性待核实"
            : "人工核验登记快照 · 非官方实时查询",
      });
    }
    return next;
  };
  window.FarmerAssistant = {
    create,
    startMedicine,
    startFollowup,
    respond,
    intent,
  };
})();
