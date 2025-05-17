const functions = require("firebase-functions");
const fetch = require("node-fetch");
const cors = require("cors")({origin: true});
const bodyParser = require("body-parser");

// API 프록시 함수
exports.apiProxy = functions.https.onRequest((req, res) => {
  cors(req, res, async () => {
    try {
      // 원본 요청 경로 유지 (예: /login, /register 등)
      const apiUrl = `http://146.56.98.203:5000${req.path}`;
      console.log(`Proxying request to: ${apiUrl}`);

      // 요청 헤더 및 본문 준비
      const headers = {
        "Content-Type": "application/json",
      };

      // 요청 옵션 구성
      const options = {
        method: req.method,
        headers: headers,
      };

      // GET 요청이 아닌 경우에만 본문 추가
      if (req.method !== "GET") {
        options.body = JSON.stringify(req.body);
      }

      // 쿼리스트링 처리
      let urlWithQuery = apiUrl;
      if (Object.keys(req.query).length > 0) {
        const queryParams = new URLSearchParams(req.query).toString();
        urlWithQuery = `${apiUrl}?${queryParams}`;
      }

      // 실제 API 요청 수행
      const response = await fetch(urlWithQuery, options);

      // 응답 데이터 처리
      const responseData = await response.json();

      // 원본 상태 코드와 함께 응답 반환
      res.status(response.status).json(responseData);
    } catch (error) {
      console.error("API 프록시 오류:", error);
      res.status(500).json({
        status: "error",
        message: "서버 내부 오류가 발생했습니다.",
        error: error.message,
      });
    }
  });
});
