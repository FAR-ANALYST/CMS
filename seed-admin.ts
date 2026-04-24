// Seeds the FAROUK super-admin account on first call.
// Idempotent: safe to invoke multiple times.
//
// Creates an auth user (email-confirmed) and assigns the 'admin' role.
// Triggered automatically by the login page when no session exists.

import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

const SUPER_ADMIN_EMAIL = "farouk@getmycoach.ug";
const SUPER_ADMIN_PASSWORD = "FAROUK2020";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const admin = createClient(supabaseUrl, serviceRoleKey);

    // 1. Find or create the auth user
    const { data: list } = await admin.auth.admin.listUsers();
    let user = list?.users?.find((u) => u.email === SUPER_ADMIN_EMAIL);

    if (!user) {
      const { data, error } = await admin.auth.admin.createUser({
        email: SUPER_ADMIN_EMAIL,
        password: SUPER_ADMIN_PASSWORD,
        email_confirm: true,
        user_metadata: { full_name: "FAROUK", role: "admin" },
      });
      if (error) throw error;
      user = data.user;
    } else {
      // Ensure password matches the documented one (in case it was changed)
      await admin.auth.admin.updateUserById(user.id, {
        password: SUPER_ADMIN_PASSWORD,
        email_confirm: true,
      });
    }

    if (!user) throw new Error("Failed to create or fetch super-admin user");

    // 2. Ensure profile row exists
    await admin
      .from("profiles")
      .upsert(
        { id: user.id, email: SUPER_ADMIN_EMAIL, full_name: "FAROUK" },
        { onConflict: "id" },
      );

    // 3. Ensure admin role is assigned
    const { data: existingRole } = await admin
      .from("user_roles")
      .select("id")
      .eq("user_id", user.id)
      .eq("role", "admin")
      .maybeSingle();

    if (!existingRole) {
      await admin.from("user_roles").insert({ user_id: user.id, role: "admin" });
    }

    return new Response(JSON.stringify({ ok: true }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("seed-admin error:", e);
    return new Response(
      JSON.stringify({ ok: false, error: (e as Error).message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
