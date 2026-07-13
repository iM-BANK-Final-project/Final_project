"""Migration guard for the retired five-axis dormancy model runner."""


def main() -> None:
    raise SystemExit(
        "기존 5축 동시감소 모델 실행은 중단되었습니다. "
        "먼저 src.preprocessing.run_persistent_transaction_weakening_labels로 "
        "Y_지속거래약화_3M70 이벤트 라벨을 생성하세요. "
        "rolling 예측 target 승인 후 모델을 재학습해야 합니다."
    )


if __name__ == "__main__":
    main()
