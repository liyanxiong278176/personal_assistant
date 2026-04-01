import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  const results: {
    timestamp: string;
    tests: any[];
    summary?: {
      total: number;
      pass: number;
      fail: number;
      success_rate: string;
    };
  } = {
    timestamp: new Date().toISOString(),
    tests: [],
  };

  try {
    // Test 1: Health Check
    results.tests.push({
      name: "1. Backend Health Check",
      status: "pending",
    });

    const healthRes = await fetch(`${API_BASE}/health`);
    const health = await healthRes.json();
    results.tests[0].status = health.status === "ok" ? "PASS" : "FAIL";
    results.tests[0].data = health;

    // Test 2: Login
    results.tests.push({
      name: "2. Login (email + password)",
      status: "pending",
    });

    const loginRes = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "test@example.com",
        password: "test123456",
      }),
    });

    if (loginRes.ok) {
      const loginData = await loginRes.json();
      results.tests[1].status = "PASS";
      results.tests[1].data = {
        user_id: loginData.user?.user_id,
        email: loginData.user?.email,
        has_access_token: !!loginData.access_token,
        has_refresh_token: !!loginData.refresh_token,
        token_type: loginData.token_type,
        expires_in: loginData.expires_in,
      };

      const accessToken = loginData.access_token;
      const refreshToken = loginData.refresh_token;

      // Test 3: Get Current User (/me)
      results.tests.push({
        name: "3. Get Current User (/me)",
        status: "pending",
      });

      const meRes = await fetch(`${API_BASE}/api/v1/auth/me`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (meRes.ok) {
        const userData = await meRes.json();
        results.tests[2].status = "PASS";
        results.tests[2].data = {
          user_id: userData.user_id,
          email: userData.email,
          username: userData.username,
        };
      } else {
        results.tests[2].status = "FAIL";
        results.tests[2].error = await meRes.text();
      }

      // Test 4: Refresh Token
      results.tests.push({
        name: "4. Refresh Token",
        status: "pending",
      });

      const refreshRes = await fetch(`${API_BASE}/api/v1/auth/refresh-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (refreshRes.ok) {
        const refreshData = await refreshRes.json();
        results.tests[3].status = "PASS";
        results.tests[3].data = {
          has_new_access_token: !!refreshData.access_token,
          token_type: refreshData.token_type,
        };
      } else {
        results.tests[3].status = "FAIL";
        results.tests[3].error = await refreshRes.text();
      }

      // Test 5: Logout
      results.tests.push({
        name: "5. Logout",
        status: "pending",
      });

      const logoutRes = await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (logoutRes.ok) {
        results.tests[4].status = "PASS";
        results.tests[4].data = await logoutRes.json();
      } else {
        results.tests[4].status = "FAIL";
        results.tests[4].error = await logoutRes.text();
      }

      // Test 6: Wrong Password
      results.tests.push({
        name: "6. Wrong Password (should fail)",
        status: "pending",
      });

      const wrongLoginRes = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "test@example.com",
          password: "wrong_password",
        }),
      });

      if (wrongLoginRes.status === 401) {
        results.tests[5].status = "PASS";
        results.tests[5].data = { correctly_rejected: true };
      } else {
        results.tests[5].status = "FAIL";
        results.tests[5].error = "Should return 401";
      }

      // Test 7: Register New User
      results.tests.push({
        name: "7. Register New User",
        status: "pending",
      });

      const registerRes = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: `test${Date.now()}@example.com`,
          password: "test123456",
          username: "testuser",
        }),
      });

      if (registerRes.ok) {
        const registerData = await registerRes.json();
        results.tests[6].status = "PASS";
        results.tests[6].data = {
          user_id: registerData.user?.user_id,
          email: registerData.user?.email,
          username: registerData.user?.username,
        };
      } else {
        const errorData = await registerRes.json();
        results.tests[6].status = "FAIL";
        results.tests[6].error = errorData;
      }
    } else {
      results.tests[1].status = "FAIL";
      results.tests[1].error = await loginRes.text();
    }

    // Summary
    const passCount = results.tests.filter((t) => t.status === "PASS").length;
    const failCount = results.tests.filter((t) => t.status === "FAIL").length;
    results.summary = {
      total: results.tests.length,
      pass: passCount,
      fail: failCount,
      success_rate: `${Math.round((passCount / results.tests.length) * 100)}%`,
    };

    return NextResponse.json(results, {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      {
        error: error.message,
        stack: error.stack,
      },
      { status: 500 }
    );
  }
}
