<p align="center"><img src="./readme_images/banner.png" width=500 /></p>

**ArXiv Digest and Personalized Recommendations using Large Language Models.**

This repo aims to provide a better daily digest for newly published arXiv papers based on your own research interests and natural-language descriptions, using relevancy ratings from GPT.

You can try it out on [Hugging Face](https://huggingface.co/spaces/AutoLLM/ArxivDigest) using your own OpenAI API key.

You can also create a daily subscription pipeline to email you the results.

## 📚 Contents

- [What this repo does](#🔍-what-this-repo-does)
  * [Examples](#some-examples)
- [Usage](#💡-usage)
  * [Running as a github action using SendGrid (Recommended)](#running-as-a-github-action-using-sendgrid-recommended)
  * [Running as a github action with SMTP credentials](#running-as-a-github-action-with-smtp-credentials)
  * [Running as a github action without emails](#running-as-a-github-action-without-emails)
  * [Running from the command line](#running-from-the-command-line)
  * [Running with a user interface](#running-with-a-user-interface)
- [Roadmap](#✅-roadmap)
- [Extending and Contributing](#💁-extending-and-contributing)

## 🔍 What this repo does

Staying up to date on [arXiv](https://arxiv.org) papers can take a considerable amount of time, with on the order of hundreds of new papers each day to filter through. There is an [official daily digest service](https://info.arxiv.org/help/subscribe.html), however large categories like [cs.AI](https://arxiv.org/list/cs.AI/recent) still have 50-100 papers a day. Determining if these papers are relevant and important to you means reading through the title and abstract, which is time-consuming.

This repository offers a method to curate a daily digest, sorted by relevance, using large language models. These models are conditioned based on your personal research interests, which are described in natural language. 

* You modify the configuration file `config.yaml` with an arXiv Subject, some set of Categories, and a natural language statement about the type of papers you are interested in.  
* The code pulls all the abstracts for papers in those categories and ranks how relevant they are to your interest on a scale of 1-10 using the model configured in `OPENAI_MODEL`.
* The code then emits an HTML digest listing all the relevant papers, and optionally emails it to you using [SendGrid](https://sendgrid.com). You will need to have a SendGrid account with an API key for this functionality to work.  

### Testing it out with Hugging Face:

We provide a demo at [https://huggingface.co/spaces/AutoLLM/ArxivDigest](https://huggingface.co/spaces/AutoLLM/ArxivDigest). Simply enter your [OpenAI API key](https://platform.openai.com/account/api-keys) and then fill in the configuration on the right. Note that we do not store your key.

![hfexample](./readme_images/hf_example.png)

You can also send yourself an email of the digest by creating a SendGrid account and [API key](https://app.SendGrid.com/settings/api_keys).

### Some examples of results:

#### Digest Configuration:
- Subject/Topic: Computer Science
- Categories: Artificial Intelligence, Computation and Language 
- Interest: 
  - Large language model pretraining and finetunings
  - Multimodal machine learning
  - Do not care about specific application, for example, information extraction, summarization, etc.
  - Not interested in paper focus on specific languages, e.g., Arabic, Chinese, etc.

#### Result:
<p align="left"><img src="./readme_images/example_1.png" width=580 /></p>

#### Digest Configuration:
- Subject/Topic: Quantitative Finance
- Interest: "making lots of money"

#### Result:
<p align="left"><img src="./readme_images/example_2.png" width=580 /></p>

## 💡 Usage

### 第三方 OpenAI-Compatible API：GitHub Actions 配置

1. 在自己的 fork 打开 **Settings → Secrets and variables → Actions → Secrets → New repository secret**，添加下列三个 **Repository secrets**：

   | 名称 | 内容 |
   | --- | --- |
   | `OPENAI_API_KEY` | 第三方服务商的 API Key |
   | `OPENAI_BASE_URL` | 该服务商文档中的 API Base URL，不包含 `/chat/completions` |
   | `OPENAI_MODEL` | 同一服务商提供的准确模型 ID |

   三项均通过工作流 `env` 传入程序；GitHub 不会自动把 Secrets 注入 Python。留空或只建在 Variables 中都会报缺少环境变量。模型名和 Base URL 本身通常不保密，这里统一使用 Secrets 便于配置。不要把真实值写进仓库。

2. 保留 `config.yaml` 中自己的分类、研究兴趣和阈值；无需在 Python 源码中写模型名。本项目保留 `openai==0.27.8`，显式把 `OPENAI_BASE_URL` 赋给旧 SDK 的 `openai.api_base`，并使用 Chat Completions。服务商和所选模型须支持 `/chat/completions`、`messages`、`max_tokens`、`temperature` 等请求参数，以及按提示词返回逐行 JSON 评分；不保证任意“兼容”或推理模型都能直接使用。

3. 提交并推送代码后，打开 **Actions → Daily pipeline → Run workflow**，选择 `main`。暂不配置邮件 Secrets，就只生成 HTML。

4. 在 **Generate Digest** 日志依次核对 `Fetched papers`、`Papers after category filter`、`Scoring papers`、`Papers at or above threshold`。成功后下载 **Artifacts → digest.html**，解压后打开 HTML。

   分类无匹配或全部低于阈值时，HTML 会明确说明原因。模型响应为空、截断或评分数量不符时，任务会失败，不能把这种失败视为“没有相关论文”。`No sendgrid api key found. Skipping email` 只表示未启用邮件，不影响生成报告。

如果使用中科大平台，官方 [API 使用说明](https://llm.ustc.edu.cn/guide/api-usage/) 给出的 Base URL 是 `https://api.llm.ustc.edu.cn/v1`；应保留 `/v1`，模型 ID 以项目当前授权列表为准。

工作流先执行 **Check API connectivity**，不带密钥访问 Base URL 下的 `/models`。收到 HTTP 401 等响应只说明网络及 HTTPS 可达，不代表密钥或模型已验证；连接超时（HTTP 000）则需要检查运行机器到平台的网络。少写 `/v1` 会造成接口路径错误，但不会解释 TCP 连接超时。GitHub 托管 runner 使用自己的网络，本机连接校园网或 VPN 不会改变它的出口；如果托管 runner 无法连接，应改用它能访问的 API，或在获准且可访问平台的机器上运行任务。不要仅靠加长超时反复重跑。

本地运行：使用 Python 3.9 或以上（Actions 使用 3.11），在仓库根目录执行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.template .env
# 仅在本地 .env 填写上述三项；.env 已被 Git 忽略。
python -m unittest discover -s tests -v
python src/action.py
```

测试使用本地模拟 HTTP 接口，不需要真实 API Key，不调用付费服务。首次恢复分类筛选后可能有数百篇候选，程序会为全部候选评分；请先确认服务商额度。

### Running as a github action using SendGrid (Recommended).

The recommended way to get started using this repository is to:

1. Fork the repository
2. Modify `config.yaml` and merge the changes into your main branch.
3. Set the following secrets [(under settings, Secrets and variables, repository secrets)](https://docs.github.com/en/actions/security-guides/encrypted-secrets#creating-encrypted-secrets-for-a-repository). See [Advanced Usage](./advanced_usage.md#create-and-fetch-your-api-keys) for more details on how to create and get OpenAi and SendGrid API keys:
   - `OPENAI_API_KEY` From your OpenAI-Compatible API provider
   - `OPENAI_BASE_URL` The provider's API base URL
   - `OPENAI_MODEL` The provider's exact model ID
   - `SENDGRID_API_KEY` From [SendGrid](https://app.SendGrid.com/settings/api_keys)
   - `FROM_EMAIL` This value must match the email you used to create the SendGrid API Key.
   - `TO_EMAIL`
4. Manually trigger the action or wait until the scheduled action takes place.

See [Advanced Usage](./advanced_usage.md) for more details, including step-by-step images, further customization, and alternate usage.

### Running with a user interface

To locally run the same UI as the Huggign Face space:
 
1. Install the requirements in `src/requirements.txt` as well as `gradio`.
2. Run `python src/app.py` and go to the local URL. From there you will be able to preview the papers from today, as well as the generated digests.
3. If you want to use a `.env` file for your secrets, you can copy `.env.template` to `.env` and then set the environment variables in `.env`.
- Note: These file may be hidden by default in some operating systems due to the dot prefix.
- The .env file is one of the files in .gitignore, so git does not track it and it will not be uploaded to the repository.
- Do not edit the original `.env.template` with your keys or your email address, since `.template.env` is tracked by git and editing it might cause you to commit your secrets.

> **WARNING:** Do not edit and commit your `.env.template` with your personal keys or email address! Doing so may expose these to the world!

## ✅ Roadmap

- [x] Support personalized paper recommendation using LLM.
- [x] Send emails for daily digest.
- [ ] Implement a ranking factor to prioritize content from specific authors.
- [ ] Support open-source models, e.g., LLaMA, Vicuna, MPT etc.
- [ ] Fine-tune an open-source model to better support paper ranking and stay updated with the latest research concepts..


## 💁 Extending and Contributing

You may (and are encourage to) modify the code in this repository to suit your personal needs. If you think your modifications would be in any way useful to others, please submit a pull request.

These types of modifications include things like changes to the prompt, different language models, or additional ways for the digest is delivered to you.
