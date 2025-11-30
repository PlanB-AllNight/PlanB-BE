#!/bin/bash

# 사용법: ./setup_data.sh [PERSONA]
# 예: ./setup_data.sh SAVER

PERSONA=${1:-BALANCE}

echo "=========================================="
echo "   PlanB 데이터 셋업 (모드: $PERSONA)"
echo "=========================================="

if [ ! -f "generate_mydata.py" ]; then
    echo "오류: generate_mydata.py 파일이 없습니다!"
    exit 1
fi

if [ -f "mydata.json" ]; then
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_name="mydata_backup_${timestamp}.json"
    echo "기존 데이터 백업 중... -> $backup_name"
    mv mydata.json "$backup_name"
fi

echo "데이터 생성 스크립트 실행..."
python3 generate_mydata.py --persona "$PERSONA"

if [ $? -ne 0 ]; then
    echo "스크립트 실행 중 오류가 발생했습니다."
    exit 1
fi

if [ -f "mydata_3months.json" ]; then
    mv mydata_3months.json mydata.json
    echo "mydata.json 생성 및 교체 완료!"
    echo ""
    echo "[파일 정보]"
    ls -lh mydata.json | awk '{print "크기: "$5", 파일명: "$9}'
else
    echo "오류: 결과 파일(mydata_3months.json)이 생성되지 않았습니다."
    exit 1
fi

echo ""
echo "완료! 서버를 재시작하거나 API를 호출하면 반영됩니다."
echo "=========================================="