// var div = document.createElement("div");
// var div2 = document.createElement("div");

// console.log(div);

// var div3 = document.querySelectorAll("div")[0];

// var a = document.querySelectorAll("div")[0];
// var b = document.querySelectorAll("span")[0];

// console.log("?????")
// console.log(a);
// console.log(a.children);
// console.log(b);

// var removed = a.removeChild(b);

// console.log(removed === b);      // true
// console.log(a.children.length); // 0
// console.log(b.children);        // 정상 (subtree 유지)


var btn = document.querySelectorAll("button")[0];
var box = document.querySelectorAll("div")[1]; // 두 번째 div (Fade Animation Box)
var is_faded = false;

btn.addEventListener("click", function (e) {
    e.preventDefault();

    // 버튼 클릭 시 style을 덮어씌워 opacity를 변경하여 애니메이션(transition) 유발
    if (is_faded) {
        box.style = "background-color: blue; color: white; opacity: 1.0; transition: opacity 1s;";
        is_faded = false;
    } else {
        box.style = "background-color: blue; color: white; opacity: 0.2; transition: opacity 1s;";
        is_faded = true;
    }
});