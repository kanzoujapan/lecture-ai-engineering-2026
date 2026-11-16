# 第4回 解答

## 演習

- 基準別の一致率（直す前）：根拠　/　、範囲　/　、ヒント　/　、分かりやすさ　/　、回の表示　/　
- 要確認の件数（直す前）：
- 直した基準と、書き足した方針：
- 基準別の一致率と要確認の件数（直した後）：
- 講師のラベルと自分のラベルで判定が違った項目と、そう判定した理由：
- 気づき・疑問：

## 宿題

**発展課題｜SWE-bench Verified**

実際のGitHubの不具合報告や機能要望を読み、修正前のコードに変更を加えて解決できるかを測るベンチマークを選んだ。AIツールを使い、公開データの問題文3件を元の修正PR・テストと照合し、審査記録から選別件数を集計した。以下の難しさは、問題を読んだ段階での見立てである。[公式データセット](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified)

### 読んだ3問

1. **Djangoで同じURL設定を二重に読み込む問題（django__django-11333）**

   URL設定を省略した場合と、同じ既定値を明示した場合でキャッシュが分かれ、URLの検索に使うオブジェクトを二重に作ってしまう。自分ならまず、この2通りで同じオブジェクトが返るかを確かめ、キャッシュに渡す前に既定値を補う。3問の中では最も手を付けやすい。LLMも例に合わせてキャッシュを1個にまとめるだけでは、別のURL設定まで混ぜてしまう。元のテストは「同じ設定なら共有する」「別の設定なら分ける」の両方を確かめていた。[問題データ](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/viewer/default/test?row=46)・[修正PRとテスト](https://github.com/django/django/pull/11333/files)

2. **Astropyでモデルを入れ子にすると、独立な入力が結び付く問題（astropy__astropy-12907）**

   2つの独立な変換を先にまとめてから別の変換と組み合わせると、各出力が両方の入力に依存するという誤った行列が返る。同じ変換を横に並べた場合は正しい。自分ならこの2通りの出力を比べて不具合を再現できそうだが、途中の行列を追わないと修正箇所は絞れない。LLMにとっても、例の行列だけを正しく返す修正と、入れ子の深さが変わっても内側の依存関係を保つ修正を区別するのが難しい。[問題データ](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/viewer/default/test?row=0)・[修正PRとテスト](https://github.com/astropy/astropy/pull/12907/files)

3. **PylintでPythonの型注釈をクラス図に反映する問題（pylint-dev__pylint-4551）**

   引数に文字列型の注釈があっても、既定値が `None` だと、クラス図から属性の型が読み取れない。自分なら、短いクラスから図を生成して型が表示されるかを確かめる。一方、採点テストは新しい内部関数 `get_annotation` を名前で読み込んでいた。その名前は問題文から推測できないため、LLMが別の関数名で同じ図を正しく出しても失敗する。ここでは実装の難しさに、採点条件を知り得ない難しさが重なっている。[問題データ](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/viewer/default/test?row=320)・[修正PRとテスト](https://github.com/pylint-dev/pylint/pull/4551/files)

### 誰がどう作り、どう採点したか

元のSWE-benchは、7人の著者が12のPythonプロジェクトから、実際に解決されたGitHubのissueと対応する修正PRを集めて作った。元のテストセットは2,294件ある。問題のもとになった報告や修正は各プロジェクトの利用者・開発者による。[原論文](https://arxiv.org/abs/2310.06770)

Verified版では、Pythonの開発経験があり、事前テストを通過した93人が品質審査を担当した。無作為に選んだ1,699件を1件につき3人が独立に読み、問題文から要求が分かるか、別の正しい解き方までテストが落としてしまわないかを調べた。3人のうち1人でも重大な問題を指摘すると除外する。公開CSVの `filter_out` 列を数えると、除外は1,160件（68.3%）、通過は539件だった。そこから修正に1時間以上かかると見積もった問題をできるだけ残し、残りを無作為に選んで500件にした。[選定手順](https://openai.com/index/introducing-swe-bench-verified/)・[審査記録のCSV（ZIP）](https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip)

モデルの解答を採点するときは、提出された変更を修正前のコードに適用し、指定のテストを実行する。もともと失敗していたテスト（`FAIL_TO_PASS`）がすべて通り、以前から成功していたテスト（`PASS_TO_PASS`）もすべて通れば、その問題を解決できたと数える。[公式の採点方法](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)

### 第4回の評価セットとの違い

| 比べる点 | 講義の評価セット | SWE-bench Verified |
|---|---|---|
| 規模と目的 | 学習支援エージェントの質問・回答10件。未知語や宿題の解答要求などを入れ、採点用LLMの判断が人と合うかを見る | 現実の開発課題500件。エージェントがコードを修正して解決できた割合を見る |
| 人の役割 | 講師1人がケースを用意。受講生は回答にラベルを付け、講師と判断が割れる項目も比べる | 開発経験者93人が参加し、各問3人で問題文とテストの妥当性を審査する |
| 採点と迷いの扱い | 根拠・範囲・ヒント・分かりやすさは人とLLMで比較し、LLMの `unsure` は人が確認する。末尾の「第N回」はコードで判定する | モデルの修正はテストで合否が決まる。正しい別解を落とすテストは、問題を選ぶ段階で見つけて除く |

講義側の件数と判定手順は[第4回の配布資料](https://github.com/matsuolab/lecture-ai-engineering-2026/blob/lec04-start/lectures/04/problem.md)で確認した。

### 気づき・疑問

第3回では、LoRAとQLoRAを説明するとき、検索1回で両方の定義が返る場合があった。「2回検索したか」を合格条件にすると、根拠のそろった回答も落としてしまう。Pylintの関数名を指定したテストにも同じ問題がある。自分がこのエージェントの評価を作るなら、検索回数の違う2つの正しい回答をあえて用意し、「両方の説明が検索結果に裏付けられている」という基準でどちらも合格するか試したい。[第3回の比較結果](https://github.com/kanzoujapan/lecture-ai-engineering-2026/blob/bbdd278/lectures/03/answer.md)

Pylintのこの問題は最初の審査を通り、後の再調査で関数名への依存が指摘された。OpenAIは再調査で不適切なテストや学習データへの混入を確認し、このベンチマークのスコア報告を終了している。3人が確認したという事実に加え、どんな正しい解答を試して採点方法を検証したのかも知りたいと思った。[OpenAIの再調査](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
