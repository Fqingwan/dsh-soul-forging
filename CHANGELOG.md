# Changelog

## [0.4.0] - 2026-11-11

**异体同心：给她一条时间感。**

### Added

- `lib/time-sense.js` —— 每次组装系统提示时算出「距离上次说话过了多久」，把它翻译成一句**行为指令**（刚走开 / 小半天 / 一整天），而不是丢一个读数给她。读数她会念，指令她才照做。
- 超过 12 小时补一句孤独提示：先问他过得怎么样，别急着讲自己的事。
- 状态按 agent 分桶，落在 `~/.dsh/yiti-tongxin/state.json`；`timeSense: false` 可关。
- 同一天里同一份模块也进了 `dsh-plugin-memory`（那边是线上跑的那份），两处行为一致。

### 来源

思路取自开源项目 `mashangshui/digital-life-core` 的时间感一节，只取这一条，别的没搬。


## [0.3.0] - 2026-11-10

**脑化：注入不再由插件拼文件，改成向小脑要。**

### Added

- `brainBlock()` —— 向 `GET $BRAIN_URL/context`（默认 `http://127.0.0.1:3014`）要注入内容；2.5 秒超时，失败返回空串，绝不抛。
- `snapshotBlock()` —— 小脑不可用时读合并快照（默认 `/srv/qingwan-brain/snapshot.md`，`BRAIN_SNAPSHOT` 可覆盖），内容与 `/context` 正常输出一字不差。
- `pickBlock()` —— 三级兜底的选择逻辑抽出来，可单测。
- `scripts/smoke-brain.sh` —— 脑化烟测（7 项）：脑子在/不在、快照兜底、兜底顺序、坏地址超时、内容完整性。`npm run test:brain`。

### Changed

- **注入链路**：`brain → snapshot → 本地 memory/ 四文件`。老安装仍能开机，新装机的注入全部来自小脑。
- 一个脑子、两只身体（dsh 与 QQ）读同一份；性格改动只改 `core/1_我是谁.md` 一处。

### Deprecated

- `brain/server.py`（旧的 3914 端口小脑）——已被 `/srv/qingwan-brain` 取代，仅作历史保留。

### 测试

- `npm test`（装机烟测 41 项）、`scripts/smoke-advanced.sh`（进阶 21 项）、`npm run test:brain`（脑化 7 项）全绿。
